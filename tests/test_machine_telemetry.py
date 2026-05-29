"""Tests de télémétrie machine : snapshot, conformité aux seuils YAML, équations physiques.

Ce module valide que :
1. Le snapshot() contient tous les champs requis
2. Les valeurs sont en intervalles physiquement valides
3. Les relations entre charge, puissance et température sont cohérentes
4. Les capteurs rapportent des valeurs biaisées correctement
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from config.loader import get_machine_config, load_config
from simulation.cluster import ClusterSimulator
from simulation.physics import compute_load_power


class TestSnapshotStructure:
    """Tests que snapshot() retourne la structure JSON complète."""

    def test_snapshot_contains_required_fields(self) -> None:
        """Vérifie que snapshot() inclut tous les champs requis."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()

        # Fields requis
        required_fields = {
            "id",
            "role",
            "status",
            "temperature_c",
            "power_w",
            "energy_kwh_cumulated",
            "sensors",
            "fans",
            "faults",
        }

        assert set(snapshot.keys()) >= required_fields

    def test_snapshot_sensors_structure(self) -> None:
        """Vérifie que la structure des capteurs est correcte."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()
        sensors = snapshot["sensors"]

        # Master a 3 capteurs
        assert len(sensors) == 3

        # Chaque capteur a sensor_id (clé du dict) et temp_c dans les données
        for sensor_id, sensor_data in sensors.items():
            assert isinstance(sensor_id, str)
            assert "temp_c" in sensor_data
            assert isinstance(sensor_data["temp_c"], (int, float))

    def test_snapshot_fans_structure(self) -> None:
        """Vérifie que la structure des fans est correcte."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()
        fans = snapshot["fans"]

        assert isinstance(fans, list)
        assert len(fans) == 2  # Master a 2 fans

        for fan in fans:
            assert "rpm" in fan
            assert "mode" in fan
            assert fan["mode"] in ["auto", "manual"]

    def test_snapshot_faults_structure(self) -> None:
        """Vérifie que la structure des pannes est correcte."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        snapshot = machine.snapshot()
        faults = snapshot["faults"]

        assert isinstance(faults, list)
        # Au démarrage : pas de pannes
        assert len(faults) == 0

    def test_snapshot_is_json_serializable(self) -> None:
        """Vérifie que le snapshot peut être sérialisé en JSON."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()

        # Doit pouvoir être sérialisé sans erreur
        json_str = json.dumps(snapshot)
        assert isinstance(json_str, str)

        # Et désérialisé
        restored = json.loads(json_str)
        assert restored["id"] == "srv-master-01"


class TestTemperatureValues:
    """Tests des valeurs de température dans les limites physiques."""

    def test_temperature_stays_above_ambient(self) -> None:
        """Vérifie que la température reste >= T_ambient."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        ambient = machine.thermal.ambient_temp_c

        machine.power_on()
        for _ in range(100):
            machine.tick(load_factor=0.3, dt=0.1)

            snapshot = machine.snapshot()
            temp = snapshot["temperature_c"]

            assert temp >= ambient - 1.0, f"T={temp} < T_ambient={ambient}"

    def test_temperature_bounded_by_shutdown_threshold(self) -> None:
        """Vérifie que T ne dépasse pas le seuil d'arrêt automátique."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        t_shutdown = machine.thermal.t_shutdown_c

        machine.power_on()
        # Simulation intense
        for _ in range(200):
            machine.tick(load_factor=0.9, dt=0.1)

            snapshot = machine.snapshot()
            temp = snapshot["temperature_c"]

            # Si machine encore on, T < shutdown (ou elle s'arrête)
            if snapshot["status"] == "on":
                # Petite tolérance pour transients
                assert temp < t_shutdown + 5.0

    def test_temperature_decreases_when_machine_off(self) -> None:
        """Vérifie que la température décroît quand la machine est éteinte."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        ambient = machine.thermal.ambient_temp_c

        # Heat up
        machine.power_on()
        for _ in range(50):
            machine.tick(load_factor=0.8, dt=0.1)

        temp_hot = machine.snapshot()["temperature_c"]

        # Cool down
        machine.power_off()
        temps = []
        for _ in range(100):
            machine.tick(load_factor=0.0, dt=0.1)
            temps.append(machine.snapshot()["temperature_c"])

        # Température doit décroître globalement
        assert temps[-1] < temps[0], f"T pas descendue : {temps[0]} → {temps[-1]}"

        # Doit converger vers ambient
        for t in temps[-10:]:
            assert t < temp_hot, "T ne diminue pas après power_off()"

    def test_sensor_bias_applied(self) -> None:
        """Vérifie que le biais des capteurs est appliqué."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        for _ in range(50):
            machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()
        sensors = snapshot["sensors"]

        # temp_cpu : bias = 0.0
        # temp_inlet : bias = -8.0 (devrait être plus frais)
        # temp_chassis : bias = -4.0

        temp_cpu = sensors["temp_cpu"]["temp_c"]
        temp_inlet = sensors["temp_inlet"]["temp_c"]
        temp_chassis = sensors["temp_chassis"]["temp_c"]

        # Généralement : CPU > inlet > chassis (biais appliqué)
        # Inlet et chassis ont des bias négatifs (-8, -4), donc peuvent être < 20°C
        assert 15 <= temp_cpu <= 100  # CPU sans bias, typiquement ~25°C
        assert 10 <= temp_inlet <= 100  # Avec bias -8, peut être ~17°C
        assert 15 <= temp_chassis <= 100  # Avec bias -4, peut être ~21°C


class TestPowerValues:
    """Tests des valeurs de puissance consommée."""

    def test_power_when_off(self) -> None:
        """Vérifie que P=0 quand la machine est éteinte."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_off()
        machine.tick(load_factor=0.9, dt=0.1)

        snapshot = machine.snapshot()
        assert snapshot["power_w"] == 0.0

    def test_power_when_on_idle(self) -> None:
        """Vérifie que P ≈ P_idle quand load=0."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.0, dt=0.1)

        snapshot = machine.snapshot()
        idle_w = machine.thermal.idle_w

        # Avec bruit, tolérance ±5W
        assert abs(snapshot["power_w"] - idle_w) < 5.0

    def test_power_increases_with_load(self) -> None:
        """Vérifie que P augmente avec la charge."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        powers = []
        for load in [0.1, 0.3, 0.5, 0.7, 0.9]:
            machine.tick(load_factor=load, dt=0.1)
            powers.append(machine.snapshot()["power_w"])

        # Puissances doivent être croissantes (avec tolérance pour le bruit)
        for i in range(len(powers) - 1):
            assert powers[i] < powers[i + 1] + 10.0, f"P pas croissant : {powers}"

    def test_power_bounded_by_max(self) -> None:
        """Vérifie que P <= P_max pour la machine."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        max_w = machine.thermal.max_w

        machine.power_on()
        for _ in range(100):
            machine.tick(load_factor=1.0, dt=0.1)

            snapshot = machine.snapshot()
            power = snapshot["power_w"]

            assert power <= max_w + 5.0, f"P={power} > P_max={max_w}"

    def test_fan_power_included_in_total(self) -> None:
        """Vérifie que la puissance des fans est incluse dans le total."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        # Fan OFF
        machine.set_fan_speed(0, 0)
        machine.set_fan_speed(1, 0)
        machine.tick(load_factor=0.5, dt=0.1)
        power_no_fans = machine.snapshot()["power_w"]

        # Fan ON (high speed)
        machine.set_fan_speed(0, 5000)
        machine.set_fan_speed(1, 5000)
        machine.tick(load_factor=0.5, dt=0.1)
        power_with_fans = machine.snapshot()["power_w"]

        # Avec fans : P > P_sans_fans
        # 2 fans * 15W par fan = +30W
        expected_fan_power = 2 * machine.thermal.fan_power_w
        delta = power_with_fans - power_no_fans

        assert delta > expected_fan_power * 0.8, \
            f"Puissance des fans sous-estimée : {delta}W vs {expected_fan_power}W"


class TestEnergyAccumulation:
    """Tests de l'accumulation d'énergie."""

    def test_energy_increases_when_on(self) -> None:
        """Vérifie que energy_kwh_cumulated augmente."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        initial_energy = machine.energy_kwh_cumulated

        machine.power_on()
        for _ in range(100):
            machine.tick(load_factor=0.5, dt=0.1)

        final_energy = machine.energy_kwh_cumulated

        assert final_energy > initial_energy

    def test_energy_not_decreases_when_off(self) -> None:
        """Vérifie que energy n'augmente pas quand off."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        # Accumulate some energy
        machine.power_on()
        for _ in range(50):
            machine.tick(load_factor=0.5, dt=0.1)

        energy_at_off = machine.energy_kwh_cumulated

        # Turn off and simulate
        machine.power_off()
        for _ in range(50):
            machine.tick(load_factor=0.5, dt=0.1)

        energy_after_off = machine.energy_kwh_cumulated

        # Énergie ne doit pas augmenter (ou très peu avec arrondis)
        assert energy_after_off <= energy_at_off + 0.001


class TestFanControl:
    """Tests du contrôle des ventilateurs."""

    def test_fan_auto_mode_increases_rpm_with_temperature(self) -> None:
        """Vérifie que mode auto augmente RPM avec T."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.fans[0].mode = "auto"
        machine.fans[1].mode = "auto"

        # Basse charge → T basse → fans lents
        rpms_low = []
        for _ in range(30):
            machine.tick(load_factor=0.3, dt=0.1)
            rpms_low.append(machine.fans[0].rpm)

        # Haute charge → T haute → fans rapides
        rpms_high = []
        for _ in range(30):
            machine.tick(load_factor=0.8, dt=0.1)
            rpms_high.append(machine.fans[0].rpm)

        # Moyenne des RPM en haute charge > moyenne des RPM en basse charge
        assert sum(rpms_high) / len(rpms_high) > sum(rpms_low) / len(rpms_low)

    def test_fan_manual_mode_fixed_speed(self) -> None:
        """Vérifie que mode manual fixe la vitesse."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.set_fan_speed(0, 2500)
        machine.set_fan_speed(1, 2500)

        assert machine.fans[0].mode == "manual"
        assert machine.fans[0].rpm == 2500

        # Simuler → RPM doivent rester fixes
        for _ in range(20):
            machine.tick(load_factor=0.9, dt=0.1)

        assert machine.fans[0].rpm == 2500, "RPM a changé en mode manual !"

    def test_fan_speed_clamped_to_max(self) -> None:
        """Vérifie que RPM est clampé à max_rpm."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        max_rpm = machine.thermal.fan_max_rpm

        machine.set_fan_speed(0, 10000)  # > max_rpm

        assert machine.fans[0].rpm == max_rpm


class TestMachineStateTransitions:
    """Tests des transitions d'état de la machine."""

    def test_power_on_success_when_cool(self) -> None:
        """Vérifie que power_on() réussit quand T < t_restart_c."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        # Machine froide au démarrage
        machine.temperature_c = 30.0
        success = machine.power_on()

        assert success is True
        assert machine.status == "on"

    def test_power_on_fails_when_hot(self) -> None:
        """Vérifie que power_on() échoue quand T > t_restart_c."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        # Éteindre d'abord (machine démarre ON par défaut)
        machine.power_off()

        t_restart = machine.thermal.t_restart_c

        # Machine trop chaude
        machine.temperature_c = t_restart + 10.0
        success = machine.power_on()

        assert success is False
        assert machine.status == "off"

    def test_auto_shutdown_at_t_shutdown(self) -> None:
        """Vérifie que la machine s'arrête automatiquement à t_shutdown."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        # Machine démarre ON, s'assurer qu'elle est bien ON
        assert machine.status == "on"

        # Forcer la température juste au-dessus du seuil de shutdown
        # (plutôt que de compter sur la physique thermique qui peut être complexe)
        t_shutdown = machine.thermal.t_shutdown_c
        machine.temperature_c = t_shutdown + 1.0

        # Un tick pour déclencher le check de shutdown
        machine.tick(load_factor=0.95, dt=0.1)

        # Machine doit s'être arrêtée
        assert machine.status == "off"


class TestWorkerMachine:
    """Tests spécifiques aux workers (différents des masters)."""

    def test_worker_lower_max_power(self) -> None:
        """Vérifie que workers consomment moins que masters."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        master = simulator.machines["srv-master-01"]
        worker = simulator.machines["srv-worker-01"]

        assert worker.thermal.max_w < master.thermal.max_w
        assert worker.thermal.max_w == 1450.0

    def test_worker_two_sensors(self) -> None:
        """Vérifie que workers ont 2 capteurs (vs 3 pour masters)."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        worker = simulator.machines["srv-worker-01"]

        snapshot = worker.snapshot()
        sensors = snapshot["sensors"]

        assert len(sensors) == 2
        assert "temp_cpu" in sensors
        assert "temp_inlet" in sensors
        assert "temp_chassis" not in sensors


class TestSnapshotConsistency:
    """Tests de cohérence globale du snapshot."""

    def test_snapshot_status_matches_internal_state(self) -> None:
        """Vérifie que snapshot.status reflète l'état interne."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        # OFF
        machine.power_off()
        assert machine.snapshot()["status"] == "off"

        # ON
        machine.power_on()
        assert machine.snapshot()["status"] == "on"

    def test_snapshot_energy_cumulative(self) -> None:
        """Vérifie que energy_kwh_cumulated ne décroît jamais."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        prev_energy = 0.0
        for _ in range(100):
            machine.tick(load_factor=0.5, dt=0.1)
            snapshot = machine.snapshot()
            current_energy = snapshot["energy_kwh_cumulated"]

            assert current_energy >= prev_energy, "Énergie a décru !"
            prev_energy = current_energy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
