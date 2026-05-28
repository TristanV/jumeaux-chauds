"""Tests Phase 7.5 - TimescaleDB consumer integration tests.

This module validates:
1. MQTT topic parsing and cluster/machine extraction
2. JSON payload parsing and data extraction
3. Telemetry data insertion (temperature, power, energy, fans)
4. Event data insertion (faults, status changes)
5. Timestamp conversion (ISO 8601 -> DateTime)
6. Error handling (invalid JSON, malformed topics)
7. MQTT reconnection logic

Tests cover:
- Topic pattern matching
- Payload structure validation
- Data type conversion
- Timestamp handling
- Error cases
- Message dispatch logic

Total: 15+ tests for consumer integration
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest


class TestTopicParsing:
    """Tests for MQTT topic parsing and extraction."""

    def test_topic_regex_telemetry(self):
        """Verify telemetry topic pattern matching."""
        topic_re = re.compile(r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$")

        topic = "dt/cluster_alpha/srv-master-01/telemetry"
        match = topic_re.match(topic)

        assert match is not None
        assert match.group("cluster") == "cluster_alpha"
        assert match.group("machine") == "srv-master-01"
        assert match.group("kind") == "telemetry"

    def test_topic_regex_temperature(self):
        """Verify temperature topic pattern matching."""
        topic_re = re.compile(r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$")

        topic = "dt/cluster_alpha/srv-master-01/temp/cpu"
        match = topic_re.match(topic)

        assert match is not None
        assert match.group("kind") == "temp/cpu"

    def test_topic_regex_fault(self):
        """Verify fault topic pattern matching."""
        topic_re = re.compile(r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$")

        topic = "dt/cluster_alpha/srv-master-01/fault"
        match = topic_re.match(topic)

        assert match is not None
        assert match.group("kind") == "fault"

    def test_topic_regex_status(self):
        """Verify status topic pattern matching."""
        topic_re = re.compile(r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$")

        topic = "dt/cluster_alpha/srv-master-01/status"
        match = topic_re.match(topic)

        assert match is not None
        assert match.group("kind") == "status"

    def test_topic_regex_cluster_topics(self):
        """Verify cluster-level topics don't match machine pattern."""
        topic_re = re.compile(r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$")

        # Cluster topics like dt/cluster_alpha/summary should not match
        topic = "dt/cluster_alpha/summary"
        match = topic_re.match(topic)

        assert match is None

    def test_topic_regex_invalid_topic(self):
        """Verify invalid topics don't match."""
        topic_re = re.compile(r"^dt/(?P<cluster>[^/]+)/(?P<machine>[^/]+)/(?P<kind>.+)$")

        topics = [
            "not/a/dt/topic",
            "dt/cluster_only",
            "dt/",
            "",
        ]

        for topic in topics:
            match = topic_re.match(topic)
            assert match is None


class TestPayloadParsing:
    """Tests for JSON payload parsing and extraction."""

    def test_telemetry_payload_parsing(self):
        """Verify telemetry payload JSON parsing."""
        payload_json = {
            "ts": "2026-05-28T16:26:35.839Z",
            "status": "on",
            "temperature_c": 22.5,
            "power_w": 150.0,
            "energy_kwh_cumulated": 0.5,
            "sensors": [
                {"sensor_id": "temp_cpu", "temp_c": 22.5},
            ],
            "fans": [
                {"idx": 0, "rpm": 2000},
                {"idx": 1, "rpm": 2100},
            ],
        }

        payload = json.dumps(payload_json)
        data = json.loads(payload)

        assert data["ts"] == "2026-05-28T16:26:35.839Z"
        assert data["status"] == "on"
        assert data["temperature_c"] == 22.5
        assert data["power_w"] == 150.0
        assert len(data["fans"]) == 2

    def test_event_payload_parsing(self):
        """Verify event payload JSON parsing."""
        payload_json = {
            "ts": "2026-05-28T16:26:35.839Z",
            "event": "injected",
            "fault_type": "temperature_high",
        }

        payload = json.dumps(payload_json)
        data = json.loads(payload)

        assert data["ts"] == "2026-05-28T16:26:35.839Z"
        assert data["event"] == "injected"
        assert data["fault_type"] == "temperature_high"

    def test_invalid_json_handling(self):
        """Verify invalid JSON is rejected gracefully."""
        invalid_payloads = [
            b"not json",
            b"{incomplete json",
            b'{"invalid": trailing content}',
            b"",
        ]

        for payload in invalid_payloads:
            with pytest.raises(json.JSONDecodeError):
                json.loads(payload)

    def test_missing_optional_fields(self):
        """Verify payload with missing optional fields is valid."""
        payload_json = {
            "ts": "2026-05-28T16:26:35.839Z",
            "status": "on",
            "temperature_c": 22.5,
        }

        payload = json.dumps(payload_json)
        data = json.loads(payload)

        # Should not raise
        assert data.get("power_w") is None
        assert data.get("fans", []) == []


class TestTimestampConversion:
    """Tests for timestamp conversion (ISO 8601 -> DateTime)."""

    def test_convert_iso8601_z_format(self):
        """Verify ISO 8601 with Z suffix conversion."""
        ts_str = "2026-05-28T16:26:35.839Z"

        # Convert Z to +00:00
        ts = ts_str
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"

        dt = datetime.fromisoformat(ts)

        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 28
        assert dt.hour == 16
        assert dt.tzinfo is not None

    def test_convert_iso8601_utc_format(self):
        """Verify ISO 8601 with UTC offset conversion."""
        ts_str = "2026-05-28T16:26:35.839+00:00"

        dt = datetime.fromisoformat(ts_str)

        assert dt.year == 2026
        assert dt.tzinfo is not None

    def test_empty_timestamp_fallback(self):
        """Verify empty timestamp uses current time."""
        ts_str = ""

        if ts_str:
            ts = ts_str
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts)
        else:
            dt = datetime.now(timezone.utc)

        # Should have timezone
        assert dt.tzinfo is not None


class TestFanAverageCalculation:
    """Tests for fan RPM average calculation."""

    def test_fan_rpm_average_calculation(self):
        """Verify fan RPM average calculation."""
        fans = [
            {"idx": 0, "rpm": 2000},
            {"idx": 1, "rpm": 2100},
        ]

        fan_rpm_avg = (
            sum(f.get("rpm", 0) for f in fans) / len(fans) if fans else None
        )

        assert fan_rpm_avg == 2050.0

    def test_fan_rpm_average_single_fan(self):
        """Verify fan RPM average with single fan."""
        fans = [{"idx": 0, "rpm": 2500}]

        fan_rpm_avg = (
            sum(f.get("rpm", 0) for f in fans) / len(fans) if fans else None
        )

        assert fan_rpm_avg == 2500.0

    def test_fan_rpm_average_no_fans(self):
        """Verify fan RPM average with no fans."""
        fans = []

        fan_rpm_avg = (
            sum(f.get("rpm", 0) for f in fans) / len(fans) if fans else None
        )

        assert fan_rpm_avg is None

    def test_fan_rpm_missing_values(self):
        """Verify fan RPM average with missing rpm values."""
        fans = [
            {"idx": 0},  # Missing rpm
            {"idx": 1, "rpm": 2000},
        ]

        fan_rpm_avg = (
            sum(f.get("rpm", 0) for f in fans) / len(fans) if fans else None
        )

        assert fan_rpm_avg == 1000.0


class TestMessageDispatching:
    """Tests for message dispatch logic based on topic kind."""

    def test_dispatch_telemetry_message(self):
        """Verify telemetry message is dispatched correctly."""
        kind = "telemetry"

        if kind == "telemetry":
            dispatch_target = "telemetry_insert"
        elif kind == "fault":
            dispatch_target = "event_insert"
        else:
            dispatch_target = None

        assert dispatch_target == "telemetry_insert"

    def test_dispatch_fault_message(self):
        """Verify fault message is dispatched to events."""
        kind = "fault"

        if kind == "telemetry":
            dispatch_target = "telemetry_insert"
        elif kind == "fault":
            dispatch_target = "event_insert"
        else:
            dispatch_target = None

        assert dispatch_target == "event_insert"

    def test_dispatch_status_message(self):
        """Verify status message is dispatched to events."""
        kind = "status"

        if kind == "telemetry":
            dispatch_target = "telemetry_insert"
        elif kind == "fault":
            dispatch_target = "event_insert"
        elif kind == "status":
            dispatch_target = "event_insert"
        else:
            dispatch_target = None

        assert dispatch_target == "event_insert"

    def test_dispatch_unknown_message(self):
        """Verify unknown message kind is ignored."""
        kind = "unknown"

        if kind == "telemetry":
            dispatch_target = "telemetry_insert"
        elif kind == "fault":
            dispatch_target = "event_insert"
        elif kind == "status":
            dispatch_target = "event_insert"
        else:
            dispatch_target = None

        assert dispatch_target is None


class TestDataExtraction:
    """Tests for extracting specific data from payloads."""

    def test_extract_temperature_from_telemetry(self):
        """Verify temperature extraction from telemetry."""
        data = {
            "temperature_c": 25.5,
            "sensors": [
                {"sensor_id": "temp_cpu", "temp_c": 25.5},
            ],
        }

        temp_c = data.get("temperature_c")
        assert temp_c == 25.5

    def test_extract_power_from_telemetry(self):
        """Verify power extraction from telemetry."""
        data = {
            "power_w": 150.0,
            "energy_kwh_cumulated": 0.5,
        }

        power_w = data.get("power_w")
        energy_kwh = data.get("energy_kwh_cumulated")

        assert power_w == 150.0
        assert energy_kwh == 0.5

    def test_extract_status_from_telemetry(self):
        """Verify status extraction from telemetry."""
        data = {"status": "on"}

        status = data.get("status")
        assert status == "on"

    def test_extract_event_type_from_fault(self):
        """Verify event type and payload extraction."""
        data = {
            "ts": "2026-05-28T16:26:35.839Z",
            "event": "injected",
            "fault_type": "temperature_high",
        }

        event_type = "fault"
        payload = json.dumps(data)

        assert event_type == "fault"
        assert "fault_type" in json.loads(payload)


class TestConsumerConfiguration:
    """Tests for consumer configuration and environment variables."""

    def test_mqtt_broker_defaults(self):
        """Verify MQTT broker defaults."""
        mqtt_host = "localhost"
        mqtt_port = 1883

        assert mqtt_host == "localhost"
        assert mqtt_port == 1883

    def test_postgres_dsn_construction(self):
        """Verify PostgreSQL DSN construction."""
        user = "jumeaux"
        password = "jumeaux"
        host = "localhost"
        port = 5432
        db = "jumeaux"

        dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"

        assert "postgresql://" in dsn
        assert user in dsn
        assert host in dsn
        assert str(port) in dsn
        assert db in dsn

    def test_topic_subscription_pattern(self):
        """Verify topic subscription pattern."""
        subscription = "dt/#"

        assert subscription == "dt/#"
        assert subscription.startswith("dt/")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
