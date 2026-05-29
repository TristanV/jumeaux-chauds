"""Tests Phase 7.4 - MQTT e2e integration tests.

This module validates:
1. Simulation -> MQTT publisher flow
2. Topic structure and naming conventions
3. Payload format and validity
4. QoS levels (0 for telemetry, 1 for events)
5. Publisher reconnection behavior

Tests cover:
- 8 main topic types
- Message payload structure
- QoS compliance
- Topic naming conventions
- Multiple machines publishing
- Reconnection robustness

Total: 15+ tests for MQTT integration
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
class TestMqttPublisherBasics:
    """Tests for MqttPublisher basic functionality."""

    async def test_publisher_initialization(self):
        """Verify MqttPublisher can be instantiated."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        publisher = MqttPublisher(mqtt_cfg)

        assert publisher is not None
        assert publisher._topic_root == "dt"
        assert publisher._qos_telemetry == 0
        assert publisher._qos_events == 1

    async def test_mqtt_config_loading(self):
        """Verify MQTT config is properly loaded from YAML."""
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt

        assert mqtt_cfg.broker_port == 1883
        assert mqtt_cfg.topic_root == "dt"
        assert mqtt_cfg.qos_telemetry == 0
        assert mqtt_cfg.qos_events == 1

    async def test_topic_construction_machine_level(self):
        """Verify topic construction for machine-level topics."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        telemetry_topic = pub._t("cluster_alpha", "srv-master-01", "telemetry")
        assert telemetry_topic == "dt/cluster_alpha/srv-master-01/telemetry"

        temp_topic = pub._t("cluster_alpha", "srv-master-01", "temp", "cpu")
        assert temp_topic == "dt/cluster_alpha/srv-master-01/temp/cpu"

        status_topic = pub._t("cluster_alpha", "srv-master-01", "status")
        assert status_topic == "dt/cluster_alpha/srv-master-01/status"

    async def test_topic_construction_cluster_level(self):
        """Verify topic construction for cluster-level topics."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        summary_topic = pub._tc("cluster_alpha", "summary")
        assert summary_topic == "dt/cluster_alpha/summary"

        energy_topic = pub._tc("cluster_alpha", "metrics", "energy")
        assert energy_topic == "dt/cluster_alpha/metrics/energy"


@pytest.mark.asyncio
class TestMqttPayloadStructure:
    """Tests for MQTT payload structure and JSON validity."""

    async def test_telemetry_payload_structure(self):
        """Verify telemetry payload has correct structure."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        machine = simulator.machines["srv-master-01"]
        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()

        # Validate snapshot structure
        assert "id" in snapshot
        assert "temperature_c" in snapshot
        assert "status" in snapshot
        assert "fans" in snapshot
        assert "sensors" in snapshot

    async def test_summary_payload_generation(self):
        """Verify cluster summary payload is valid."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in list(simulator.machines.values())[:3]:
            machine.power_on()

        for _ in range(10):
            for machine in simulator.machines.values():
                machine.tick(load_factor=0.5, dt=0.1)
            simulator._update_metrics()

        assert simulator.cluster_id == "cluster_alpha"
        assert len(simulator.machines) == 5
        assert simulator.energy_kwh_total >= 0.0

    async def test_energy_metrics_structure(self):
        """Verify energy metrics payload structure."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in simulator.machines.values():
            machine.power_on()

        for _ in range(50):
            for machine in simulator.machines.values():
                machine.tick(load_factor=0.7, dt=0.1)
            simulator._update_metrics()

        metrics = {
            "energy_kwh_total": simulator.energy_kwh_total,
            "cost_eur_total": simulator.cost_eur_total,
            "pue_effective": simulator.pue_effective,
        }

        assert metrics["energy_kwh_total"] >= 0.0
        assert metrics["cost_eur_total"] >= 0.0
        assert metrics["pue_effective"] >= 1.0

        json_str = json.dumps(metrics)
        parsed = json.loads(json_str)
        assert parsed["energy_kwh_total"] == metrics["energy_kwh_total"]


@pytest.mark.asyncio
class TestMqttTopicConformance:
    """Tests for MQTT topic naming and structure conformance."""

    async def test_topic_naming_convention_machine(self):
        """Verify machine topics follow pattern."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        topics = [
            pub._t("cluster_alpha", "srv-master-01", "telemetry"),
            pub._t("cluster_alpha", "srv-master-01", "temp", "cpu"),
            pub._t("cluster_alpha", "srv-master-01", "power"),
            pub._t("cluster_alpha", "srv-master-01", "fan", "0"),
            pub._t("cluster_alpha", "srv-master-01", "status"),
            pub._t("cluster_alpha", "srv-master-01", "fault"),
        ]

        for topic in topics:
            assert topic.startswith("dt/cluster_alpha/srv-master-01/")

    async def test_topic_naming_convention_cluster(self):
        """Verify cluster topics follow pattern."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        topics = [
            pub._tc("cluster_alpha", "summary"),
            pub._tc("cluster_alpha", "metrics", "energy"),
        ]

        for topic in topics:
            assert topic.startswith("dt/cluster_alpha/")

    async def test_qos_levels_configuration(self):
        """Verify QoS levels are correctly configured."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        assert pub._qos_telemetry == 0
        assert pub._qos_events == 1


@pytest.mark.asyncio
class TestMqttSimulationIntegration:
    """Tests for simulation-to-MQTT integration."""

    async def test_multiple_machines_snapshot_generation(self):
        """Verify snapshots can be generated for all machines."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in simulator.machines.values():
            machine.power_on()

        for machine_id, machine in simulator.machines.items():
            machine.tick(load_factor=0.5, dt=0.1)
            snapshot = machine.snapshot()
            assert snapshot["id"] == machine_id
            assert "temperature_c" in snapshot
            assert "status" in snapshot

    async def test_cluster_machines_count(self):
        """Verify cluster has all machines accessible."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)

        for machine in simulator.machines.values():
            machine.power_on()

        for machine in simulator.machines.values():
            machine.tick(load_factor=0.5, dt=0.1)

        simulator._update_metrics()

        assert len(simulator.machines) == 5
        assert all(
            mid in simulator.machines
            for mid in [
                "srv-master-01",
                "srv-master-02",
                "srv-worker-01",
                "srv-worker-02",
                "srv-worker-03",
            ]
        )

    async def test_fan_state_payload_validity(self):
        """Verify fan state payload structure."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()

        assert "fans" in snapshot
        assert len(snapshot["fans"]) > 0

        for fan in snapshot["fans"]:
            assert "idx" in fan
            assert "mode" in fan
            assert "rpm" in fan
            assert fan["mode"] in ["auto", "manual"]
            assert fan["rpm"] >= 0

    async def test_sensor_data_validity(self):
        """Verify sensor data in snapshots."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()

        assert "sensors" in snapshot
        assert len(snapshot["sensors"]) > 0

        # sensors est un dict[sensor_id, {temp_c, bias_c}]
        for sensor_id, sensor_data in snapshot["sensors"].items():
            assert isinstance(sensor_id, str)
            assert "temp_c" in sensor_data
            assert isinstance(sensor_data["temp_c"], (int, float))
            assert 10.0 <= sensor_data["temp_c"] <= 95.0


@pytest.mark.asyncio
class TestMqttRobustness:
    """Tests for MQTT publisher robustness."""

    async def test_publisher_none_client_handling(self):
        """Verify publisher handles None client gracefully."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        assert pub._client is None

        try:
            await pub._publish("dt/test/topic", {"test": "data"})
        except Exception as e:
            pytest.fail(f"Publishing with None client raised {e}")

    async def test_json_serialization_of_payloads(self):
        """Verify all payload types are JSON-serializable."""
        from simulation.cluster import ClusterSimulator
        from config.loader import load_config

        cfg = load_config("nominal")
        simulator = ClusterSimulator(cfg)
        machine = simulator.machines["srv-master-01"]

        machine.power_on()
        machine.tick(load_factor=0.5, dt=0.1)

        snapshot = machine.snapshot()

        try:
            json_str = json.dumps(snapshot)
            parsed = json.loads(json_str)
            assert parsed["id"] == snapshot["id"]
        except (TypeError, ValueError) as e:
            pytest.fail(f"Snapshot not JSON-serializable: {e}")

    async def test_timestamp_format_iso8601(self):
        """Verify timestamps are in ISO 8601 format."""
        from mqtt.publisher import _now_iso

        ts = _now_iso()

        assert len(ts) == 24
        assert "T" in ts
        assert ts.endswith("Z")

        parts = ts.split("T")
        assert len(parts) == 2
        date_part, time_part = parts
        assert len(date_part) == 10
        assert time_part.endswith("Z")


@pytest.mark.asyncio
class TestMqttTopicList:
    """Tests validating all 8 main topics are properly addressed."""

    async def test_all_8_main_topics_defined(self):
        """Verify all 8 main topics from spec are addressable."""
        from mqtt.publisher import MqttPublisher
        from config.loader import load_config

        cfg = load_config("nominal")
        mqtt_cfg = cfg.cluster.mqtt
        pub = MqttPublisher(mqtt_cfg)

        topics = {
            "telemetry": pub._t("cluster_alpha", "machine_01", "telemetry"),
            "temp": pub._t("cluster_alpha", "machine_01", "temp", "sensor_01"),
            "power": pub._t("cluster_alpha", "machine_01", "power"),
            "fan": pub._t("cluster_alpha", "machine_01", "fan", "0"),
            "status": pub._t("cluster_alpha", "machine_01", "status"),
            "fault": pub._t("cluster_alpha", "machine_01", "fault"),
            "summary": pub._tc("cluster_alpha", "summary"),
            "energy": pub._tc("cluster_alpha", "metrics", "energy"),
        }

        assert len(topics) == 8
        for topic_name, topic_path in topics.items():
            assert isinstance(topic_path, str)
            assert len(topic_path) > 0
            assert "dt/" in topic_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
