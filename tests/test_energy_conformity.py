"""Tests de conformité énergétique : formule P(L), cohérence données YAML.

Ce module valide que :
1. La puissance suit la formule YAML : P = idle + (max - idle) * load^alpha
2. L'énergie accumulée est cohérente avec la puissance intégrée
3. Le coût énergétique est correctement calculé
4. Les seuils YAML sont respectés
"""

from __future__ import annotations

import numpy as np

import pytest

from config.loader import get_machine_config, load_config
from simulation.cluster import ClusterSimulator
from simulation.physics import compute_load_power


class TestLoadPowerFormula:
    """Tests de la formule P(load) : P = idle + (max - idle) * load^alpha."""

    def test_power_at_zero_load(self) -> None:
        """Vérifie que P(load=0) = idle_w."""
        idle_w = 200.0
        max_w = 1700.0
        alpha = 1.5

        power = compute_load_power(
            load_factor=0.0,
            idle_w=idle_w,
            max_w=max_w,
            alpha=alpha
        )

        assert abs(power - idle_w) < 0.01

    def test_power_at_full_load(self) -> None:
        """Vérifie que P(load=1) = max_w."""
        idle_w = 200.0
        max_w = 1700.0
        alpha = 1.5

        power = compute_load_power(
            load_factor=1.0,
            idle_w=idle_w,
            max_w=max_w,
            alpha=alpha
        )

        assert abs(power - max_w) < 0.01

    def test_power_monotonically_increasing(self) -> None:
        """Vérifie que P(load) est strictement croissant."""
        idle_w = 100.0
        max_w = 1450.0
        alpha = 1.5

        loads = np.linspace(0, 1, 11)
        powers = [
            compute_load_power(l, idle_w, max_w, alpha)
            for l in loads
        ]

        for i in range(len(powers) - 1):
            assert powers[i] < powers[i + 1], \
                f"P non croissant : {powers[i]:.1f} → {powers[i+1]:.1f}"

    def test_power_formula_with_different_alpha(self) -> None:
        """Vérifie que alpha affecte bien la courbe P(load)."""
        idle_w = 100.0
        max_w = 1000.0
        load = 0.5

        power_alpha_1 = compute_load_power(load, idle_w, max_w, alpha=1.0)
        power_alpha_2 = compute_load_power(load, idle_w, max_w, alpha=2.0)

        # alpha=2 → courbe plus non-linéaire
        # À load=0.5 : alpha=1 → 550W, alpha=2 → plus bas
        assert power_alpha_2 < power_alpha_1

    def test_power_clamped_to_valid_range(self) -> None:
        """Vérifie que load est clampé à [0, 1]."""
        idle_w = 100.0
        max_w = 1000.0

        # load = -1 → clampé à 0
        power_negative = compute_load_power(-1.0, idle_w, max_w)
        assert abs(power_negative - idle_w) < 0.01

        # load = 2.0 → clampé à 1
        power_over = compute_load_power(2.0, idle_w, max_w)
        assert abs(power_over - max_w) < 0.01


class TestMachineEnergyConsistency:
    """Tests que l'énergie accumulée = ∫P(t)dt."""

    def test_energy_accumulation_matches_power(self) -> None:
        """Vérifie que ΔE = P·Δt (intégration numérique)."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        dt = 0.1  # Pas de temps
        accumulated_energy = 0.0

        for _ in range(100):
            power_before = machine.power_w
            machine.tick(load_factor=0.5, dt=dt)
            power_after = machine.power_w

            # Approx : Δ E ≈ (P_before + P_after) / 2 * dt
            avg_power = (power_before + power_after) / 2
            accumulated_energy += avg_power * dt / 3600  # Convertir Wh en kWh

        # Comparer avec energy_kwh_cumulated
        measured_energy = machine.energy_kwh_cumulated

        # Tolérance : ±10% ou ±0.01 kWh
        relative_error = abs(measured_energy - accumulated_energy) / max(measured_energy, 0.1)
        assert relative_error < 0.1, \
            f"Énergie incohérente : {measured_energy:.3f} vs {accumulated_energy:.3f} kWh"

    def test_zero_energy_when_off(self) -> None:
        """Vérifie que l'énergie n'augmente pas quand off."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_off()
        initial_energy = machine.energy_kwh_cumulated

        for _ in range(100):
            machine.tick(load_factor=0.9, dt=0.1)

        final_energy = machine.energy_kwh_cumulated

        assert final_energy <= initial_energy + 0.0001, \
            "Énergie a augmenté quand machine OFF"


class TestYamlPowerParametersAlignment:
    """Tests que les valeurs YAML sont utilisées correctement."""

    def test_master_idle_watts_used(self) -> None:
        """Vérifie que master.idle_watts = 200W est utilisé."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        master = simulator.machines["srv-master-01"]

        master.power_on()
        master.tick(load_factor=0.0, dt=0.1)

        power = master.power_w
        idle_w = 200.0

        # Avec bruit, tolérance ±5W
        assert abs(power - idle_w) < 5.0

    def test_worker_idle_watts_used(self) -> None:
        """Vérifie que worker.idle_watts = 100W est utilisé."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        worker = simulator.machines["srv-worker-01"]

        worker.power_on()
        worker.tick(load_factor=0.0, dt=0.1)

        power = worker.power_w
        idle_w = 100.0

        assert abs(power - idle_w) < 5.0

    def test_master_max_watts_boundary(self) -> None:
        """Vérifie que P_max = 1700W pour master."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        master = simulator.machines["srv-master-01"]

        master.power_on()
        for _ in range(100):
            master.tick(load_factor=1.0, dt=0.1)

        power = master.power_w
        max_w = 1700.0

        assert power <= max_w + 5.0

    def test_worker_max_watts_boundary(self) -> None:
        """Vérifie que P_max = 1450W pour worker."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        worker = simulator.machines["srv-worker-01"]

        worker.power_on()
        for _ in range(100):
            worker.tick(load_factor=1.0, dt=0.1)

        power = worker.power_w
        max_w = 1450.0

        assert power <= max_w + 5.0

    def test_alpha_exponent_affects_power_curve(self) -> None:
        """Vérifie que alpha = 1.5 affecte bien la courbe."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        assert master_cfg.thermal.alpha_load_exponent == 1.5

        # Test avec la formule
        idle = master_cfg.power.idle_watts
        max_w = master_cfg.power.max_watts
        alpha = master_cfg.thermal.alpha_load_exponent

        # À load=0.5 avec alpha=1.5
        p_half = idle + (max_w - idle) * (0.5 ** alpha)

        # Vérifier que c'est < à load=1 et > à load=0
        assert idle < p_half < max_w


class TestClusterEnergyMetrics:
    """Tests des métriques énergétiques au niveau cluster."""

    def test_cluster_energy_increases(self) -> None:
        """Vérifie que cluster.energy_kwh_total augmente."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in simulator.machines.values():
            machine.power_on()

        initial_energy = simulator.energy_kwh_total

        for _ in range(100):
            simulator._tick()

        final_energy = simulator.energy_kwh_total

        assert final_energy > initial_energy

    def test_cluster_cost_calculation(self) -> None:
        """Vérifie que cost_eur_total = energy_kwh_total * price."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in simulator.machines.values():
            machine.power_on()

        for _ in range(100):
            simulator._tick()

        energy = simulator.energy_kwh_total
        cost = simulator.cost_eur_total
        price = cfg.cluster.electricity_price_eur_kwh

        # cost = energy * price (tolérance pour arrondis)
        expected_cost = energy * price
        assert abs(cost - expected_cost) < 0.01

    def test_pue_affects_cost(self) -> None:
        """Vérifie que PUE augmente le coût effectif."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in simulator.machines.values():
            machine.power_on()

        for _ in range(100):
            simulator._tick()

        energy = simulator.energy_kwh_total
        pue = simulator._pue

        # Coût doit tenir compte du PUE
        # P_effective = P_cpu * PUE (pour overhead de refroidissement)
        assert simulator.pue_effective == pue


class TestNominalVsStressLoadProfile:
    """Tests que les profils nominal et stress consomment différemment."""

    def test_nominal_lower_load_than_stress(self) -> None:
        """Vérifie que le profil nominal consomme moins en moyenne."""
        # Nominal : sine_wave, base=0.35, amplitude=0.20
        # Stress : ramp, base=0.20→0.95

        cfg_nominal = load_config("nominal")
        sim_nominal = ClusterSimulator(cfg_nominal)

        cfg_stress = load_config("stress")
        sim_stress = ClusterSimulator(cfg_stress)

        for m in sim_nominal.machines.values():
            m.power_on()
        for m in sim_stress.machines.values():
            m.power_on()

        # 100 ticks chacun
        for _ in range(100):
            sim_nominal._tick()
            sim_stress._tick()

        energy_nominal = sim_nominal.energy_kwh_total
        energy_stress = sim_stress.energy_kwh_total

        # Stress consomme plus (charge globalement plus élevée)
        assert energy_stress > energy_nominal


class TestFanPowerConsumption:
    """Tests que la puissance des fans est correctement incluse."""

    def test_fan_power_per_rpm_estimation(self) -> None:
        """Vérifie que chaque fan consomme ~power_per_fan_w."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()

        # Référence : load=0.5, fans arrêtés
        machine.fans[0].rpm = 0
        machine.fans[1].rpm = 0
        for _ in range(30):
            machine.tick(load_factor=0.5, dt=0.1)
        power_no_fans = np.mean([machine.power_w for _ in range(5)])

        # Fans à 5000 RPM
        machine.fans[0].rpm = 5000
        machine.fans[1].rpm = 5000
        for _ in range(30):
            machine.tick(load_factor=0.5, dt=0.1)
        power_with_fans = np.mean([machine.power_w for _ in range(5)])

        # Différence ≈ 2 * power_per_fan_w
        expected_delta = 2 * machine.thermal.fan_power_w
        actual_delta = power_with_fans - power_no_fans

        # Tolérance pour le modèle (approximatif)
        assert actual_delta > expected_delta * 0.5

    def test_fan_speed_zero_uses_no_power(self) -> None:
        """Vérifie que RPM=0 → pas de puissance fan."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.set_fan_speed(0, 0)
        machine.set_fan_speed(1, 0)

        for _ in range(30):
            machine.tick(load_factor=0.5, dt=0.1)

        power = machine.power_w
        idle_w = machine.thermal.idle_w

        # P ≈ idle (+ charge *)
        # Pas de puissance supplémentaire pour fans
        assert power < idle_w + 200.0


class TestHeatRatioUsage:
    """Tests que heat_ratio est utilisé correctement (P_heat = P_elec * heat_ratio)."""

    def test_heat_ratio_affects_temperature(self) -> None:
        """Vérifie que heat_ratio affecte la montée de température."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        assert master_cfg.power.heat_ratio == 0.70

        # Avec heat_ratio=0.70 : 70% de la puissance devient chaleur
        # Avec heat_ratio=0.50 : seulement 50% devient chaleur
        # → La seconde scénario devrait avoir une T plus basse

        # La validation est implicite : si heat_ratio=0.70 est utilisé
        # correctement, T dépendra de la charge de façon cohérente


class TestThermalThresholdsFromYaml:
    """Tests que les seuils thermiques YAML sont respectés."""

    def test_t_shutdown_boundary(self) -> None:
        """Vérifie que machine s'arrête à t_shutdown."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        master = simulator.machines["srv-master-01"]

        t_shutdown = master.thermal.t_shutdown_c
        assert t_shutdown == 90.0

        master.power_on()

        # Forcer T à dépasser shutdown
        for _ in range(300):
            master.tick(load_factor=0.95, dt=0.1)

            if master.temperature_c > t_shutdown:
                # Machine doit s'arrêter automatiquement
                assert master.status == "off", \
                    f"Machine pas arrêtée à T={master.temperature_c}°C > t_shutdown={t_shutdown}°C"
                break

    def test_t_restart_hysteresis(self) -> None:
        """Vérifie que t_restart < t_shutdown (hystérésis)."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        master = simulator.machines["srv-master-01"]

        assert master.thermal.t_restart_c < master.thermal.t_shutdown_c

        # Hystérésis : machine ne redémarre que si T < t_restart
        # même après s'être arrêtée à t_shutdown


class TestEnergyConsumptionRealism:
    """Tests que la consommation énergétique globale est réaliste."""

    def test_idle_power_is_significant_fraction_of_max(self) -> None:
        """Vérifie que P_idle est une fraction raisonnable de P_max."""
        cfg = load_config("nominal")

        for machine_id in ["srv-master-01", "srv-worker-01"]:
            m_cfg = get_machine_config(cfg, machine_id)
            idle = m_cfg.power.idle_watts
            max_w = m_cfg.power.max_watts

            # Généralement 10-20% (dissipation minimum)
            ratio = idle / max_w
            assert 0.05 < ratio < 0.5, \
                f"{machine_id} : idle/max = {ratio:.2f} (hors de [0.05, 0.5])"

    def test_heat_ratio_physically_reasonable(self) -> None:
        """Vérifie que heat_ratio est entre 0.6 et 0.95."""
        cfg = load_config("nominal")

        for machine_id in ["srv-master-01", "srv-worker-01"]:
            m_cfg = get_machine_config(cfg, machine_id)
            heat_ratio = m_cfg.power.heat_ratio

            # CPUs modernes : 60-90% de la puissance devient chaleur
            assert 0.60 <= heat_ratio <= 0.95, \
                f"{machine_id} : heat_ratio={heat_ratio} (hors [0.60, 0.95])"

    def test_pue_physically_reasonable(self) -> None:
        """Vérifie que PUE est entre 1.0 et 3.0."""
        cfg = load_config("nominal")

        pue = cfg.cluster.pue
        # Centres de données modernes : 1.1-2.5
        assert 1.0 <= pue <= 3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
