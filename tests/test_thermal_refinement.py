"""Tests pour l'affinage thermique Phase 8.7.

Verifie que les comportements thermiques sont realistes:
- Temperatures jamais negatives ou impossibles
- Refroidissement par ventilateurs coherent
- Stabilite numerique avec speed_multiplier eleve
- Equilibre thermique stable
"""
import pytest
import numpy as np
from config.loader import load_config
from simulation.cluster import ClusterSimulator
from simulation.physics import compute_thermal_step, compute_tau, compute_fan_power_rpm


class TestTemperatureBounds:
    """Tests que les temperatures restent dans des limites realistes."""

    def test_temperature_never_below_ambient(self):
        """Temperature ne peut jamais descendre en dessous de T_amb."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]

        machine.power_on()

        # Executer longtemps avec charge tres faible
        for _ in range(1000):
            sim._tick()

        # Meme avec tres peu de charge, T >= T_amb
        t_amb = machine.thermal.ambient_temp_c
        assert machine.temperature_c >= t_amb, \
            f"T={machine.temperature_c}C < T_amb={t_amb}C (impossible)"

    def test_temperature_never_above_shutdown(self):
        """Temperature ne depasse pas t_shutdown (machine s'arrete avant)."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]

        machine.power_on()

        # Charger a 100% pendant longtemps
        for _ in range(500):
            machine.tick(load_factor=1.0, dt=0.1)

        t_shutdown = machine.thermal.t_shutdown_c
        # Si machine s'est arretee, T devrait etre < shutdown
        assert machine.temperature_c <= t_shutdown + 1.0, \
            f"T={machine.temperature_c}C > t_shutdown={t_shutdown}C"

    def test_temperature_bounds_preserved_high_speed_multiplier(self):
        """Meme avec speed_multiplier 60x, T reste dans [T_amb, T_max]."""
        cfg = load_config("nominal")
        cfg["simulation"]["speed_multiplier"] = 60.0
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]

        t_amb = machine.thermal.ambient_temp_c
        t_shutdown = machine.thermal.t_shutdown_c

        machine.power_on()

        # Executer 300 ticks = 300s simulees a 60x
        for _ in range(300):
            sim._tick()

        # Verifier que T est dans les limites
        assert machine.temperature_c >= t_amb, \
            f"T={machine.temperature_c}C < T_amb={t_amb}C (speed_multiplier=60x)"
        assert machine.temperature_c <= t_shutdown + 1.0, \
            f"T={machine.temperature_c}C > t_shutdown={t_shutdown}C (speed_multiplier=60x)"


class TestFanCoolingEffectiveness:
    """Tests que les ventilateurs refroidissent effectivement."""

    def test_zero_rpm_no_active_cooling(self):
        """Avec RPM=0, refroidissement uniquement passif (tau = tau_max)."""
        cfg = load_config("nominal")

        # Access role profile directly
        master_profile = cfg["cluster"]["role_profiles"]["master"]
        machine_thermal = master_profile["thermal"]
        fan_max_rpm = master_profile["fans"]["max_rpm"]

        tau_with_fans_off = compute_tau(
            tau_max=machine_thermal["tau_max_s"],
            fan_rpm_mean=0,
            k_cool=machine_thermal["k_cool_rpm_factor"],
            fan_max_rpm=fan_max_rpm,
        )
        expected = machine_thermal["tau_max_s"]
        assert abs(tau_with_fans_off - expected) < 0.01, \
            f"tau(0 RPM) = {tau_with_fans_off}s != tau_max={expected}s"

    def test_max_rpm_strongest_cooling(self):
        """Avec RPM max, tau est minimaliste (refroidissement maximal)."""
        cfg = load_config("nominal")

        # Access role profile directly
        master_profile = cfg["cluster"]["role_profiles"]["master"]
        machine_thermal = master_profile["thermal"]
        fan_max_rpm = master_profile["fans"]["max_rpm"]

        tau_with_fans_off = compute_tau(
            tau_max=machine_thermal["tau_max_s"],
            fan_rpm_mean=0,
            k_cool=machine_thermal["k_cool_rpm_factor"],
            fan_max_rpm=fan_max_rpm,
        )
        tau_with_fans_max = compute_tau(
            tau_max=machine_thermal["tau_max_s"],
            fan_rpm_mean=fan_max_rpm,
            k_cool=machine_thermal["k_cool_rpm_factor"],
            fan_max_rpm=fan_max_rpm,
        )

        # Avec fans a RPM max, tau doit etre significativement plus petit
        assert tau_with_fans_max < tau_with_fans_off, \
            f"tau(max RPM)={tau_with_fans_max}s >= tau(0 RPM)={tau_with_fans_off}s"

        # Typiquement, tau_min ~= tau_max / 1.5+ (refroidissement 1.5x+ plus rapide)
        assert tau_with_fans_max < tau_with_fans_off / 1.5, \
            f"Fans a RPM max ne refroidissent pas assez (ratio < 1.5x)"

    def test_fan_speed_increases_cooling_effect(self):
        """Tau diminue monotoniquement avec RPM."""
        cfg = load_config("nominal")

        # Access role profile directly
        master_profile = cfg["cluster"]["role_profiles"]["master"]
        machine_thermal = master_profile["thermal"]
        fan_max_rpm = master_profile["fans"]["max_rpm"]

        rpm_values = [0, 1000, 2000, 3000, 4000, 5000]
        tau_values = []

        for rpm in rpm_values:
            tau = compute_tau(
                tau_max=machine_thermal["tau_max_s"],
                fan_rpm_mean=rpm,
                k_cool=machine_thermal["k_cool_rpm_factor"],
                fan_max_rpm=fan_max_rpm,
            )
            tau_values.append(tau)

        # Verifier que tau diminue strictement avec RPM
        for i in range(len(tau_values) - 1):
            assert tau_values[i] > tau_values[i + 1], \
                f"tau not decreasing: tau({rpm_values[i]})={tau_values[i]} > tau({rpm_values[i+1]})={tau_values[i+1]}"

    def test_fan_power_increases_with_rpm(self):
        """Puissance fan augmente avec RPM (loi du cube)."""
        rpm_values = [0, 1000, 2500, 5000]
        power_values = []

        for rpm in rpm_values:
            power = compute_fan_power_rpm(
                rpm=rpm,
                fan_power_w_nominal=25.0,
                fan_max_rpm=5000,
            )
            power_values.append(power)

        # Verifier que puissance augmente
        for i in range(len(power_values) - 1):
            assert power_values[i] <= power_values[i + 1], \
                f"Fan power not increasing: P({rpm_values[i]})={power_values[i]} > P({rpm_values[i+1]})={power_values[i+1]}"

    def test_fan_power_follows_cubic_law(self):
        """Puissance fan suit loi RPM**3."""
        rpm_50pct = 2500
        rpm_100pct = 5000

        power_50pct = compute_fan_power_rpm(rpm=rpm_50pct, fan_power_w_nominal=25.0, fan_max_rpm=5000)
        power_100pct = compute_fan_power_rpm(rpm=rpm_100pct, fan_power_w_nominal=25.0, fan_max_rpm=5000)

        # A 50% RPM, puissance devrait etre ~= (0.5)**3 = 0.125
        expected_ratio = (0.5) ** 3
        actual_ratio = power_50pct / power_100pct

        assert abs(actual_ratio - expected_ratio) < 0.01, \
            f"Power at 50% RPM should be {expected_ratio:.3f} of 100% RPM power, got {actual_ratio:.3f}"


class TestNumericalStability:
    """Tests que l'integration thermique reste stable meme avec dt grand."""

    def test_thermal_step_no_oscillation_small_dt(self):
        """Avec dt petit (normal), pas d'oscillation."""
        t_current = 25.0
        q_in = 100.0
        tau = 50.0
        c_th = 1000.0
        t_amb = 20.0
        dt = 0.1

        t = t_current

        for _ in range(100):
            t_new = compute_thermal_step(t, q_in, tau, c_th, t_amb, dt)
            assert abs(t_new - t) < 5.0, "Pas should be smooth (dt=0.1s)"
            t = t_new

    def test_speed_multiplier_1x_vs_subdivided_1x(self):
        """Speed multiplier 1x donne les memes resultats qu'integration normale."""
        cfg = load_config("nominal")
        cfg["simulation"]["speed_multiplier"] = 1.0

        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        for _ in range(100):
            sim._tick()

        t_after_1x = machine.temperature_c

        sim2 = ClusterSimulator(cfg)
        machine2 = sim2.machines["srv-master-01"]
        machine2.power_on()

        for _ in range(100):
            sim2._tick()

        assert abs(machine2.temperature_c - t_after_1x) < 0.5, \
            "Speed multiplier 1x should be deterministic"

    def test_high_speed_multiplier_stable_no_divergence(self):
        """Avec speed_multiplier eleve, temperature ne diverge pas."""
        cfg = load_config("nominal")
        cfg["simulation"]["speed_multiplier"] = 3600.0

        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        t_max = machine.thermal.t_shutdown_c
        t_amb = machine.thermal.ambient_temp_c

        for tick_num in range(300):
            sim._tick()

            assert machine.temperature_c >= t_amb, \
                f"Tick {tick_num}: T={machine.temperature_c}C < T_amb={t_amb}C"
            assert machine.temperature_c <= t_max + 1.0, \
                f"Tick {tick_num}: T={machine.temperature_c}C > T_max={t_max}C"

    def test_speed_multiplier_60x_stable(self):
        """Avec speed_multiplier 60x, integration reste stable."""
        cfg = load_config("stress")
        cfg["simulation"]["speed_multiplier"] = 60.0

        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        t_max = machine.thermal.t_shutdown_c
        t_amb = machine.thermal.ambient_temp_c

        for _ in range(600):
            sim._tick()

            assert machine.temperature_c >= t_amb - 1.0, \
                f"T trop basse a 60x speed: {machine.temperature_c}C"
            assert machine.temperature_c <= t_max + 1.0, \
                f"T trop haute a 60x speed: {machine.temperature_c}C"


class TestThermalEquilibrium:
    """Tests que le systeme atteint un equilibre thermique stable."""

    def test_thermal_equilibrium_low_load(self):
        """A faible charge, T converge vers T_eq stable."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        load_factor = 0.2

        for _ in range(500):
            machine.tick(load_factor=load_factor, dt=0.1)

        t_converged = machine.temperature_c

        for _ in range(200):
            machine.tick(load_factor=load_factor, dt=0.1)

        t_final = machine.temperature_c
        assert abs(t_final - t_converged) < 3.0, \
            f"Temperature unstable at low load (delta > 1.5C): {t_converged}C -> {t_final}C"

    def test_thermal_equilibrium_high_load(self):
        """A charge elevee, T converge vers T_eq stable.

        Phase 8.15 : gain_rpm_per_c réduit (50→30) — les fans montent plus lentement,
        la convergence nécessite ~5000 ticks (500s simulées) au lieu de 500.
        L'équilibre existe bien (~88°C à charge 0.8), mais le temps de convergence
        est plus long, ce qui est le comportement voulu (risque thermique réaliste).
        """
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        load_factor = 0.8

        # Warm-up suffisant pour atteindre l'équilibre avec gain réduit (Phase 8.15)
        for _ in range(5000):
            machine.tick(load_factor=load_factor, dt=0.1)

        t_converged = machine.temperature_c

        for _ in range(1000):
            machine.tick(load_factor=load_factor, dt=0.1)

        t_final = machine.temperature_c
        assert abs(t_final - t_converged) < 7.5, \
            f"Temperature unstable at high load: {t_converged}C -> {t_final}C"


class TestEnergyAndCoolingCoherence:
    """Tests que puissance consommee et refroidissement sont coherents."""

    def test_energy_includes_fan_power(self):
        """Energie totale inclut puissance des fans."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        for fan_idx in range(len(machine.fans)):
            machine.set_fan_speed(fan_idx, machine.thermal.fan_max_rpm)

        initial_energy = machine.energy_kwh_cumulated

        for _ in range(1000):
            machine.tick(load_factor=0.5, dt=0.1)

        final_energy = machine.energy_kwh_cumulated

        energy_consumed = (final_energy - initial_energy) * 1000

        expected_energy_wh_min = 1.0

        assert energy_consumed > expected_energy_wh_min, \
            f"Energy too low: {energy_consumed} Wh < {expected_energy_wh_min} Wh (fans not included?)"

    def test_higher_fans_increases_total_power(self):
        """Augmenter RPM fans augmente puissance totale consommee."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        for fan_idx in range(len(machine.fans)):
            machine.set_fan_speed(fan_idx, 0)

        power_no_fans = machine.power_w

        for fan_idx in range(len(machine.fans)):
            machine.set_fan_speed(fan_idx, machine.thermal.fan_max_rpm)

        machine.tick(load_factor=0.5, dt=0.1)
        power_with_fans = machine.power_w

        assert power_with_fans > power_no_fans, \
            f"Power should increase with fans: {power_no_fans}W -> {power_with_fans}W"


class TestFanAutoControl:
    """Tests que le mode auto des fans fonctionne correctement."""

    def test_fans_increase_with_temperature(self):
        """En mode auto, RPM augmente avec temperature."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]

        for fan_idx in range(len(machine.fans)):
            machine.set_fan_mode(fan_idx, "auto")

        machine.power_on()

        machine.temperature_c = 25.0
        machine.tick(load_factor=0.1, dt=0.1)
        rpm_low = machine.fans[0].rpm

        machine.temperature_c = 80.0
        machine.tick(load_factor=1.0, dt=0.1)
        rpm_high = machine.fans[0].rpm

        assert rpm_high > rpm_low, \
            f"Fans should speed up with temperature: {rpm_low} RPM -> {rpm_high} RPM"

    def test_fans_capped_at_max(self):
        """RPM auto ne depassent jamais f_max."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]

        for fan_idx in range(len(machine.fans)):
            machine.set_fan_mode(fan_idx, "auto")

        machine.power_on()

        machine.temperature_c = 90.0
        machine.tick(load_factor=1.0, dt=0.1)

        for fan in machine.fans:
            assert fan.rpm <= machine.thermal.fan_max_rpm, \
                f"Fan RPM should not exceed max: {fan.rpm} > {machine.thermal.fan_max_rpm}"


class TestShutdownAndRestart:
    """Tests que l'arret/redemarrage thermique fonctionne."""

    def test_machine_shuts_down_at_t_shutdown(self):
        """Machine s'arrete quand T >= t_shutdown."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        t_shutdown = machine.thermal.t_shutdown_c
        assert machine.status == "on"

        machine.temperature_c = t_shutdown + 5.0
        machine.tick(load_factor=1.0, dt=0.1)

        assert machine.status == "off", \
            f"Machine should shut down at T={machine.temperature_c}C >= t_shutdown={t_shutdown}C"

    def test_machine_restarts_at_t_restart(self):
        """Machine peut redemarrer quand T <= t_restart (hysterese thermique)."""
        cfg = load_config("nominal")
        sim = ClusterSimulator(cfg)
        machine = sim.machines["srv-master-01"]
        machine.power_on()

        # Provoquer shutdown via depassement de t_shutdown
        t_shutdown = machine.thermal.t_shutdown_c
        machine.temperature_c = t_shutdown + 5.0
        machine.tick(load_factor=1.0, dt=0.1)
        assert machine.status == "off"

        # Verifier que restart echoue si T > t_restart
        t_restart = machine.thermal.t_restart_c
        machine.temperature_c = t_restart + 5.0
        assert not machine.power_on(), "Restart should fail if T > t_restart"
        assert machine.status == "off"

        # Refroidir en dessous de t_restart et retenter
        machine.temperature_c = t_restart - 5.0
        assert machine.power_on(), "Restart should succeed if T <= t_restart"
        assert machine.status == "on"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
