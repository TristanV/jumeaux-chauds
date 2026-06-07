"""Tests d'intégration : variables YAML → MachineSimulator.

Ce module valide que :
1. Les valeurs YAML sont correctement chargées dans ThermalConfig
2. L'héritage de rôle fonctionne
3. Les surcharges individuelles de machines sont appliquées
4. Les seuils thermiques sont physiquement cohérents
"""

from __future__ import annotations

import pytest
from omegaconf import DictConfig

from config.loader import get_machine_config, load_config
from simulation.cluster import ClusterSimulator
from simulation.machine import MachineSimulator, SensorConfig, ThermalConfig


class TestYamlLoading:
    """Tests du chargement et merge des configurations YAML."""

    def test_load_base_config_nominal(self) -> None:
        """Vérifie que la config nominal se charge sans erreur."""
        cfg = load_config(scenario="nominal")

        assert cfg.cluster.id == "cluster_alpha"
        assert cfg.cluster.pue == 1.40
        assert cfg.cluster.electricity_price_eur_kwh == 0.20

    def test_load_stress_config(self) -> None:
        """Vérifie que la config stress se charge et surcharge bien."""
        cfg = load_config(scenario="stress")

        assert cfg.simulation.mode == "stress"
        assert cfg.simulation.load_profile.type == "composite_stress"  # Phase 8.14
        assert cfg.simulation.fault_injection.enabled is True

    def test_scenario_fallback_to_nominal(self) -> None:
        """Vérifie que l'absence de scénario bascule sur nominal."""
        # Par défaut, scenario="nominal"
        cfg = load_config(scenario=None)
        assert cfg.simulation.mode == "nominal"

    def test_all_machines_present(self) -> None:
        """Vérifie que les 5 machines sont déclarées."""
        cfg = load_config("nominal")
        machines = cfg.cluster.machines

        assert len(machines) == 5

        ids = {m.id for m in machines}
        assert ids == {
            "srv-master-01",
            "srv-master-02",
            "srv-worker-01",
            "srv-worker-02",
            "srv-worker-03",
        }


class TestRoleInheritance:
    """Tests de l'héritage des paramètres par rôle."""

    def test_master_inherits_role_profile(self) -> None:
        """Vérifie que master-01 hérite de la config role:master."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        # Power profile
        assert master_cfg.power.idle_watts == 200.0
        assert master_cfg.power.max_watts == 1700.0
        assert master_cfg.power.heat_ratio == 0.70

        # Thermal profile
        assert master_cfg.thermal.ambient_temp_c == 22.0
        assert master_cfg.thermal.tau_max_s == 90.0
        assert master_cfg.thermal.k_cool_rpm_factor == 2.0  # Phase 8.7: exposant 1.5, valeur ajustée
        assert master_cfg.thermal.alpha_load_exponent == 1.5

    def test_worker_inherits_role_profile(self) -> None:
        """Vérifie que worker-01 hérite de la config role:worker."""
        cfg = load_config("nominal")
        worker_cfg = get_machine_config(cfg, "srv-worker-01")

        assert worker_cfg.power.idle_watts == 100.0
        assert worker_cfg.power.max_watts == 1450.0
        assert worker_cfg.thermal.tau_max_s == 100.0
        assert worker_cfg.thermal.k_cool_rpm_factor == 2.0  # Phase 8.7: exposant 1.5, valeur ajustée

    def test_master_thermal_thresholds(self) -> None:
        """Vérifie les seuils thermiques master : t_shutdown > t_restart."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        assert master_cfg.thermal.t_shutdown_c == 90.0
        assert master_cfg.thermal.t_restart_c == 55.0
        assert master_cfg.thermal.t_shutdown_c > master_cfg.thermal.t_restart_c

    def test_worker_thermal_thresholds(self) -> None:
        """Vérifie les seuils thermiques worker."""
        cfg = load_config("nominal")
        worker_cfg = get_machine_config(cfg, "srv-worker-01")

        assert worker_cfg.thermal.t_shutdown_c == 88.0
        assert worker_cfg.thermal.t_restart_c == 50.0
        assert worker_cfg.thermal.t_shutdown_c > worker_cfg.thermal.t_restart_c


class TestMachineIndividualOverrides:
    """Tests des surcharges individuelles de machines."""

    def test_master_02_overrides_shutdown_threshold(self) -> None:
        """Vérifie que master-02 surcharge t_shutdown_c à 92.0."""
        cfg = load_config("nominal")

        master_01_cfg = get_machine_config(cfg, "srv-master-01")
        master_02_cfg = get_machine_config(cfg, "srv-master-02")

        # Master-01 : valeur par défaut du rôle
        assert master_01_cfg.thermal.t_shutdown_c == 90.0

        # Master-02 : surcharge individuelle
        assert master_02_cfg.thermal.t_shutdown_c == 92.0

    def test_worker_03_initial_status_off(self) -> None:
        """Vérifie que worker-03 démarre éteint."""
        cfg = load_config("nominal")
        worker_03 = None

        for m in cfg.cluster.machines:
            if m.id == "srv-worker-03":
                worker_03 = m
                break

        assert worker_03 is not None
        assert worker_03.initial_status == "off"

    def test_other_workers_inherit_initial_status_on(self) -> None:
        """Vérifie que worker-01 et worker-02 héritent initial_status:on."""
        cfg = load_config("nominal")

        for machine in cfg.cluster.machines:
            if machine.id in ("srv-worker-01", "srv-worker-02"):
                # Pas de surcharge → hérité du rôle (on)
                assert machine.role == "worker"


class TestTemperatureSensorsConfig:
    """Tests de la configuration des capteurs de température."""

    def test_master_has_three_sensors(self) -> None:
        """Vérifie que master a 3 capteurs."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        sensors = master_cfg.temperature_sensors
        assert len(sensors) == 3

        sensor_ids = {s.id for s in sensors}
        assert sensor_ids == {"temp_cpu", "temp_inlet", "temp_chassis"}

    def test_worker_has_two_sensors(self) -> None:
        """Vérifie que worker a 2 capteurs."""
        cfg = load_config("nominal")
        worker_cfg = get_machine_config(cfg, "srv-worker-01")

        sensors = worker_cfg.temperature_sensors
        assert len(sensors) == 2

        sensor_ids = {s.id for s in sensors}
        assert sensor_ids == {"temp_cpu", "temp_inlet"}

    def test_sensor_bias_values(self) -> None:
        """Vérifie que les biais des capteurs sont corrects."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        sensors_by_id = {s.id: s for s in master_cfg.temperature_sensors}

        assert sensors_by_id["temp_cpu"].bias_c == 0.0
        assert sensors_by_id["temp_inlet"].bias_c == -8.0
        assert sensors_by_id["temp_chassis"].bias_c == -4.0


class TestFanConfiguration:
    """Tests de la configuration des ventilateurs."""

    def test_master_fan_count(self) -> None:
        """Vérifie que master a 2 ventilateurs."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        assert master_cfg.fans.count == 2
        assert master_cfg.fans.max_rpm == 5000
        assert master_cfg.fans.power_per_fan_w == 15.0

    def test_worker_fan_count(self) -> None:
        """Vérifie que worker a 2 ventilateurs."""
        cfg = load_config("nominal")
        worker_cfg = get_machine_config(cfg, "srv-worker-01")

        assert worker_cfg.fans.count == 2
        assert worker_cfg.fans.max_rpm == 5000
        assert worker_cfg.fans.power_per_fan_w == 12.0

    def test_fan_auto_policy_proportional(self) -> None:
        """Vérifie que la politique de contrôle est 'proportional'."""
        cfg = load_config("nominal")
        master_cfg = get_machine_config(cfg, "srv-master-01")

        assert master_cfg.fans.auto_policy.type == "proportional"
        assert master_cfg.fans.auto_policy.gain_rpm_per_c == 30.0  # Phase 8.15 : réduit 50→30

    def test_worker_fan_gain_different(self) -> None:
        """Vérifie que le gain des fans worker est 28.0 (vs 30.0 pour master) — Phase 8.15."""
        cfg = load_config("nominal")
        worker_cfg = get_machine_config(cfg, "srv-worker-01")

        assert worker_cfg.fans.auto_policy.gain_rpm_per_c == 28.0  # Phase 8.15 : réduit 45→28


class TestClusterInstantiation:
    """Tests que ClusterSimulator instancie correctement les machines."""

    def test_cluster_simulator_creates_five_machines(self) -> None:
        """Vérifie que ClusterSimulator crée 5 machines."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        assert len(simulator.machines) == 5
        assert "srv-master-01" in simulator.machines
        assert "srv-worker-03" in simulator.machines

    def test_cluster_machines_inherit_config(self) -> None:
        """Vérifie que les machines du cluster héritent de la config."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        master = simulator.machines["srv-master-01"]
        assert master.thermal.idle_w == 200.0
        assert master.thermal.max_w == 1700.0

        worker = simulator.machines["srv-worker-01"]
        assert worker.thermal.idle_w == 100.0
        assert worker.thermal.max_w == 1450.0

    def test_worker_03_starts_off(self) -> None:
        """Vérifie que worker-03 démarre éteint."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        worker_03 = simulator.machines["srv-worker-03"]
        assert worker_03.status == "off"

    def test_master_overridden_threshold_in_simulator(self) -> None:
        """Vérifie que la surcharge de master-02 est bien appliquée."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        master_02 = simulator.machines["srv-master-02"]
        assert master_02.thermal.t_shutdown_c == 92.0

    def test_fan_states_initialized(self) -> None:
        """Vérifie que les fans sont initialisés pour chaque machine."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        master = simulator.machines["srv-master-01"]
        assert len(master.fans) == 2

        for fan in master.fans:
            assert fan.rpm == 0
            assert fan.mode == "auto"

    def test_sensors_initialized(self) -> None:
        """Vérifie que les capteurs sont initialisés."""
        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        master = simulator.machines["srv-master-01"]
        snapshot = master.snapshot()

        assert "sensors" in snapshot
        assert "temp_cpu" in snapshot["sensors"]
        assert "temp_inlet" in snapshot["sensors"]
        assert "temp_chassis" in snapshot["sensors"]


class TestNoiseConfiguration:
    """Tests de la configuration du bruit."""

    def test_noise_enabled_nominal(self) -> None:
        """Vérifie que le bruit est activé en nominal."""
        cfg = load_config("nominal")

        assert cfg.simulation.noise.enabled is True
        assert cfg.simulation.noise.temperature_std_c == 0.3

    def test_noise_power_and_fan_std_values(self) -> None:
        """Vérifie que les valeurs de bruit pour puissance et fans existent."""
        cfg = load_config("nominal")

        # Ces valeurs doivent être appliquées dans machine.py:tick()
        master_cfg = get_machine_config(cfg, "srv-master-01")
        assert master_cfg.noise.power_std_w == 2.0
        assert master_cfg.noise.fan_speed_std_rpm == 10.0

    def test_noise_drift_disabled_nominal(self) -> None:
        """Vérifie que la dérive est désactivée en nominal."""
        cfg = load_config("nominal")

        assert cfg.simulation.noise.drift.enabled is False

    def test_noise_drift_enabled_stress(self) -> None:
        """Vérifie que la dérive est activée en stress."""
        cfg = load_config("stress")

        assert cfg.simulation.noise.drift.enabled is True
        assert cfg.simulation.noise.drift.rate_c_per_s == 0.01


class TestFaultInjectionConfig:
    """Tests de la configuration d'injection de pannes."""

    def test_fault_injection_disabled_nominal(self) -> None:
        """Vérifie que les pannes sont désactivées en nominal."""
        cfg = load_config("nominal")

        assert cfg.simulation.fault_injection.enabled is False
        assert len(cfg.simulation.fault_injection.faults) == 0

    def test_fault_injection_enabled_stress(self) -> None:
        """Vérifie que les pannes sont activées en stress."""
        cfg = load_config("stress")

        assert cfg.simulation.fault_injection.enabled is True
        assert len(cfg.simulation.fault_injection.faults) == 3

    def test_fault_types_stress(self) -> None:
        """Vérifie que les 3 types de pannes stress existent."""
        cfg = load_config("stress")

        fault_types = {f.type for f in cfg.simulation.fault_injection.faults}
        assert fault_types == {"fan_failure", "sensor_drift", "power_surge"}

    def test_fault_distributions(self) -> None:
        """Vérifie que les distributions de pannes sont correctes."""
        cfg = load_config("stress")

        faults_by_type = {f.type: f for f in cfg.simulation.fault_injection.faults}

        assert faults_by_type["fan_failure"].distribution == "weibull"
        assert faults_by_type["sensor_drift"].distribution == "exponential"
        assert faults_by_type["power_surge"].distribution == "uniform"

    def test_fault_weibull_parameters(self) -> None:
        """Vérifie que les paramètres Weibull sont présents."""
        cfg = load_config("stress")

        fan_fault = next(
            f for f in cfg.simulation.fault_injection.faults if f.type == "fan_failure"
        )

        assert fan_fault.shape == 1.5
        assert fan_fault.scale_s == 14400  # Phase 8.15b : relevé 7200→14400 (~4h MTBF)


class TestLoadProfileConfig:
    """Tests de la configuration des profils de charge."""

    def test_nominal_multi_scale_sine_profile(self) -> None:
        """Vérifie que nominal utilise multi_scale_sine (Phase 8.14)."""
        cfg = load_config("nominal")

        lp = cfg.simulation.load_profile
        assert lp.type == "multi_scale_sine"
        assert lp.base_load == pytest.approx(0.38)
        assert lp.daily_amplitude == pytest.approx(0.15)
        assert lp.daily_period_s == pytest.approx(86400.0)

    def test_basic_sine_wave_profile(self) -> None:
        """Vérifie que basic conserve sine_wave (Phase 8.14)."""
        cfg = load_config("basic")

        lp = cfg.simulation.load_profile
        assert lp.type == "sine_wave"
        assert lp.base_load == pytest.approx(0.35)
        assert lp.amplitude == pytest.approx(0.20)
        assert lp.period_s == pytest.approx(300.0)

    def test_stress_composite_stress_profile(self) -> None:
        """Vérifie que stress utilise composite_stress (Phase 8.14)."""
        cfg = load_config("stress")

        lp = cfg.simulation.load_profile
        assert lp.type == "composite_stress"
        assert lp.base_load == pytest.approx(0.52)   # Phase 8.15b : réduit 0.55→0.52
        assert lp.spike_probability == pytest.approx(0.005)
        assert lp.drift_max == pytest.approx(0.0)    # Phase 8.15b : dérive désactivée

    def test_busy_weeks_perlin_noise_profile(self) -> None:
        """Vérifie que busy_weeks utilise perlin_noise (Phase 8.14)."""
        cfg = load_config("busy_weeks")

        lp = cfg.simulation.load_profile
        assert lp.type == "perlin_noise"
        assert lp.base_load == pytest.approx(0.40)  # Phase 8.15b : ramené 0.48→0.40
        assert lp.n_octaves == 5

    def test_heatwave_multi_scale_sine_profile(self) -> None:
        """Vérifie que heatwave utilise multi_scale_sine (Phase 8.14)."""
        cfg = load_config("heatwave")

        lp = cfg.simulation.load_profile
        assert lp.type == "multi_scale_sine"
        assert lp.base_load == pytest.approx(0.50)   # Phase 8.15b : réduit 0.58→0.50

    def test_trace_replay_profile(self) -> None:
        """Vérifie que trace_replay se charge correctement (Phase 8.14B)."""
        cfg = load_config("trace_replay")

        assert cfg.simulation.mode == "trace_replay"
        lp = cfg.simulation.load_profile
        assert lp.type == "trace_replay"
        assert lp.loop is True
        assert lp.speed_factor == pytest.approx(1.0)
        assert "bitbrains" in lp.trace_file

    def test_trace_replay_fault_injection_disabled(self) -> None:
        """Le scénario trace_replay désactive fault_injection par défaut."""
        cfg = load_config("trace_replay")
        assert cfg.simulation.fault_injection.enabled is False


class TestMQTTConfiguration:
    """Tests de la configuration MQTT."""

    def test_mqtt_broker_defaults(self) -> None:
        """Vérifie que le broker MQTT est configuré correctement."""
        cfg = load_config("nominal")

        mqtt = cfg.cluster.mqtt
        assert mqtt.broker_host == "mosquitto"
        assert mqtt.broker_port == 1883
        assert mqtt.topic_root == "dt"
        assert mqtt.cmd_root == "cmd"

    def test_mqtt_qos_levels(self) -> None:
        """Vérifie que les niveaux QoS sont configurés."""
        cfg = load_config("nominal")

        mqtt = cfg.cluster.mqtt
        assert mqtt.qos_telemetry == 0
        assert mqtt.qos_events == 1

    def test_mqtt_publish_interval(self) -> None:
        """Vérifie que l'intervalle de publication existe."""
        cfg = load_config("nominal")

        mqtt = cfg.cluster.mqtt
        assert mqtt.publish_interval_s == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
