"""Tests Phase 7.2 - Corrections et ameliorations du simulateur.

Ce module valide que :
1. power_std_w et fan_speed_std_rpm sont maintenant exploites (bruit applique)
2. Puissance des ventilateurs depend du RPM (loi du cube RPM^3)
3. Constante de temps thermique tau depend des RPM (refroidissement actif)
4. protocol_version a ete documente/supprime

Phase 7.2 Change Log :
- OK Ajouter du bruit sur power_w (gaussian_noise avec power_std_w)
- OK Ajouter modele RPM^3 pour puissance des ventilateurs
- OK Integrer compute_tau pour dependance RPM -> refroidissement
- OK Charger power_std_w et fan_speed_std_rpm depuis le YAML
- OK Documenter/supprimer protocol_version (jamais utilise)
"""

from __future__ import annotations

import numpy as np
import pytest

from config.loader import get_machine_config, load_config
from simulation.cluster import ClusterSimulator
from simulation.physics import compute_fan_power_rpm, compute_tau


class TestPhase72FanPowerModel:
    """Tests du modele de puissance des ventilateurs (RPM^3)."""

    def test_fan_power_zero_rpm_is_zero(self) -> None:
        """Verifie que P_fan(0 RPM) = 0 W."""
        power = compute_fan_power_rpm(
            rpm=0,
            fan_power_w_nominal=15.0,
            fan_max_rpm=5000,
        )
        assert power == 0.0

    def test_fan_power_max_rpm_is_nominal(self) -> None:
        """Verifie que P_fan(max_rpm) = P_nominal."""
        power = compute_fan_power_rpm(
            rpm=5000,
            fan_power_w_nominal=15.0,
            fan_max_rpm=5000,
        )
        assert abs(power - 15.0) < 0.01

    def test_fan_power_half_rpm_is_1_8_of_nominal(self) -> None:
        """Verifie que P_fan(rpm/2) = P_nominal × (1/2)^3 = 1/8."""
        power = compute_fan_power_rpm(
            rpm=2500,
            fan_power_w_nominal=16.0,
            fan_max_rpm=5000,
        )
        expected = 16.0 * (0.5 ** 3)
        assert abs(power - expected) < 0.01

    def test_fan_power_scales_cubic_with_rpm(self) -> None:
        """Verifie que la puissance augmente avec le cube du RPM."""
        nominal = 15.0
        max_rpm = 5000

        powers = {}
        for pct in [0, 25, 50, 75, 100]:
            rpm = int((pct / 100.0) * max_rpm)
            power = compute_fan_power_rpm(rpm, nominal, max_rpm)
            powers[pct] = power

        assert powers[0] < 0.01
        assert 1.5 < powers[50] < 2.2
        assert 14.5 < powers[100] < 15.5


class TestPhase72NoiseApplication:
    """Tests que le bruit power_std_w est applique."""

    def test_power_has_noise_when_enabled(self) -> None:
        """Verifie que power_w fluctue avec noise_std_w."""
        cfg = load_config("stress")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        powers = []
        for _ in range(100):
            machine.tick(load_factor=0.5, dt=0.1)
            powers.append(machine.power_w)

        unique_powers = len(set(round(p, 1) for p in powers))
        assert unique_powers > 1, "Bruit non applique sur power_w"

        variance = np.var(powers)
        assert variance > 0.0, "Aucune variance sur power_w"

    def test_master_has_power_noise_in_stress(self) -> None:
        """Verifie que stress.yaml configure bien power_std_w."""
        cfg = load_config("stress")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        noise_cfg = master_cfg.get("noise", {})
        power_std = noise_cfg.get("power_std_w", 0.0)

        assert power_std > 0.0, f"power_std_w absent ou zero : {power_std}"

    def test_power_std_w_loaded_in_thermal_config(self) -> None:
        """Verifie que power_std_w est charge dans ThermalConfig."""
        cfg = load_config("stress")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        assert hasattr(machine.thermal, "power_std_w")
        assert machine.thermal.power_std_w > 0.0


class TestPhase72ThermalTauDependsOnRpm:
    """Tests que tau depend maintenant des RPM."""

    def test_tau_decreases_with_rpm(self) -> None:
        """Verifie que tau(rpm) = tau_max / (1 + k_cool × rpm/1000)."""
        tau_max = 90.0
        k_cool = 3.5

        taus = {}
        for rpm in [0, 1000, 2500, 5000]:
            tau = compute_tau(tau_max, float(rpm), k_cool)
            taus[rpm] = tau

        assert taus[0] > taus[1000]
        assert taus[1000] > taus[2500]
        assert taus[2500] > taus[5000]

        tau_0 = taus[0]
        tau_5000 = taus[5000]

        assert abs(tau_0 - 90.0) < 0.1
        assert tau_5000 < 10.0

    def test_rpm_dependency_in_tau_formula(self) -> None:
        """Verifie que tau depend des RPM via la formule implemen."""
        tau_1000 = compute_tau(tau_max=100.0, fan_rpm_mean=1000.0, k_cool=3.0)
        tau_5000 = compute_tau(tau_max=100.0, fan_rpm_mean=5000.0, k_cool=3.0)

        assert tau_5000 < tau_1000, "Tau doit diminuer avec RPM"


class TestPhase72FanEnergyModel:
    """Tests du modele d'energie et RPM^3."""

    def test_compute_energy_with_rpm_power_list(self) -> None:
        """Verifie que compute_energy_kwh supporte fan_power_w_by_rpm."""
        from simulation.physics import compute_energy_kwh

        fan_powers = [5.0, 8.0]
        energy_advanced = compute_energy_kwh(
            power_w=500.0,
            fan_count=2,
            fan_power_w_by_rpm=fan_powers,
            tick_rate_hz=10.0,
        )

        energy_simple = compute_energy_kwh(
            power_w=500.0,
            fan_count=2,
            fan_power_w=6.5,
            tick_rate_hz=10.0,
        )

        assert abs(energy_advanced - energy_simple) / energy_simple < 0.05

    def test_fan_power_scales_with_rpm_cube(self) -> None:
        """Verifie que P_fan proportionnel RPM^3 est implementé."""
        power_slow = compute_fan_power_rpm(rpm=1000, fan_power_w_nominal=15.0, fan_max_rpm=5000)
        power_fast = compute_fan_power_rpm(rpm=5000, fan_power_w_nominal=15.0, fan_max_rpm=5000)

        ratio = power_fast / power_slow if power_slow > 0 else float('inf')

        assert ratio > 100, f"RPM cube scaling not correct: power ratio {ratio}"


class TestPhase72ProtocolVersionRemoved:
    """Tests que protocol_version a ete supprime."""

    def test_protocol_version_not_in_yaml_config(self) -> None:
        """Verifie que protocol_version n'est plus dans base.yaml."""
        cfg = load_config("nominal")

        assert "protocol_version" not in cfg.cluster.mqtt

    def test_protocol_version_removed_from_mqtt_config(self) -> None:
        """Verifie que protocol_version n'est pas attendu."""
        cfg = load_config("nominal")

        mqtt_cfg = cfg.cluster.mqtt
        assert "broker_host" in mqtt_cfg
        assert "broker_port" in mqtt_cfg
        assert "protocol_version" not in mqtt_cfg


class TestPhase72RegressionSuite:
    """Tests de regression pour s'assurer que les corrections ne cassent rien."""

    def test_cluster_still_works_with_changes(self) -> None:
        """Verifie que le cluster fonctionne toujours avec les corrections."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        assert len(simulator.machines) == 5

        for machine in simulator.machines.values():
            machine.power_on()

        dt = 0.1
        for _ in range(50):
            load_factor = 0.5
            for machine in simulator.machines.values():
                machine.tick(load_factor=load_factor, dt=dt)
            simulator._update_metrics()

        assert simulator.energy_kwh_total > 0.0
        assert simulator.cost_eur_total > 0.0

    def test_energy_accumulation_still_monotone(self) -> None:
        """Verifie que l'energie reste monotone croissante."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        prev_energy = 0.0
        for _ in range(100):
            machine.tick(load_factor=0.5, dt=0.1)
            current_energy = machine.energy_kwh_cumulated

            assert current_energy >= prev_energy - 0.00001
            prev_energy = current_energy

    def test_temperature_still_respects_thresholds(self) -> None:
        """Verifie que les seuils thermiques sont encore respectes."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        t_shutdown = machine.thermal.t_shutdown_c
        t_ambient = machine.thermal.ambient_temp_c

        machine.power_on()

        for _ in range(300):
            machine.tick(load_factor=0.9, dt=0.1)

            assert machine.temperature_c >= t_ambient - 1.0
            if machine.temperature_c > t_shutdown:
                assert machine.status == "off"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
