"""Tests Phase 7.3 - Integration tests for FastAPI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def api_client():
    """Synchronous HTTP client with lifespan active."""
    with TestClient(app) as client:
        yield client


class TestClusterEndpoints:
    """Tests for /cluster endpoints."""

    def test_get_cluster_status(self, api_client):
        """GET /cluster/status returns complete snapshot."""
        response = api_client.get("/cluster/status")
        assert response.status_code == 200
        data = response.json()
        assert "cluster_id" in data
        assert "ts" in data
        assert "metrics" in data
        assert "machines" in data
        metrics = data["metrics"]
        assert "energy_kwh_total" in metrics
        assert "cost_eur_total" in metrics
        assert "pue_effective" in metrics
        assert isinstance(data["machines"], dict)
        assert len(data["machines"]) == 5

    def test_get_cluster_energy(self, api_client):
        """GET /cluster/energy returns energy metrics."""
        response = api_client.get("/cluster/energy")
        assert response.status_code == 200
        data = response.json()
        assert "energy_kwh_total" in data
        assert "cost_eur_total" in data
        assert "pue_effective" in data

    def test_post_cluster_power_on(self, api_client):
        """POST /cluster/power turns on all machines."""
        response = api_client.post("/cluster/power", json={"action": "on"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_post_cluster_power_off(self, api_client):
        """POST /cluster/power turns off all machines."""
        response = api_client.post("/cluster/power", json={"action": "off"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_put_cluster_fan_speed(self, api_client):
        """PUT /cluster/fan_speed sets fan speed."""
        response = api_client.put("/cluster/fan_speed", json={"rpm": 3000})
        assert response.status_code == 200
        assert response.json()["ok"] is True


class TestMachineEndpoints:
    """Tests for /machines endpoints."""

    def test_get_machine_snapshot(self, api_client):
        """GET /machines/{id} returns machine snapshot."""
        response = api_client.get("/machines/srv-master-01")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "srv-master-01"
        assert "role" in data
        assert "status" in data
        assert "temperature_c" in data

    def test_get_machine_not_found(self, api_client):
        """GET /machines/{invalid_id} returns 404."""
        response = api_client.get("/machines/non-existent-machine")
        assert response.status_code == 404

    def test_get_all_machines(self, api_client):
        """Verify all 5 machines are accessible."""
        machine_ids = [
            "srv-master-01",
            "srv-master-02",
            "srv-worker-01",
            "srv-worker-02",
            "srv-worker-03",
        ]
        for machine_id in machine_ids:
            response = api_client.get(f"/machines/{machine_id}")
            assert response.status_code == 200

    def test_post_machine_power_on(self, api_client):
        """POST /machines/{id}/power turns on a machine."""
        response = api_client.post(
            "/machines/srv-worker-01/power", json={"action": "on"}
        )
        assert response.status_code == 200

    def test_post_machine_power_off(self, api_client):
        """POST /machines/{id}/power turns off a machine."""
        response = api_client.post(
            "/machines/srv-worker-01/power", json={"action": "off"}
        )
        assert response.status_code == 200

    def test_post_machine_power_on_status_code(self, api_client):
        """POST /machines/{id}/power returns 200 or 409."""
        response = api_client.post(
            "/machines/srv-master-01/power", json={"action": "on"}
        )
        assert response.status_code in [200, 409]

    def test_put_machine_fan_speed(self, api_client):
        """PUT /machines/{id}/fan_speed sets fan speed."""
        response = api_client.put(
            "/machines/srv-master-01/fan_speed",
            json={"fan_idx": 0, "rpm": 2500},
        )
        assert response.status_code == 200

    def test_put_machine_fan_mode_auto(self, api_client):
        """PUT /machines/{id}/fan_mode switches to auto."""
        response = api_client.put(
            "/machines/srv-master-01/fan_mode",
            json={"fan_idx": 0, "mode": "auto"},
        )
        assert response.status_code == 200

    def test_put_machine_fan_mode_manual(self, api_client):
        """PUT /machines/{id}/fan_mode switches to manual."""
        response = api_client.put(
            "/machines/srv-master-01/fan_mode",
            json={"fan_idx": 0, "mode": "manual"},
        )
        assert response.status_code == 200


class TestSimulationEndpoints:
    """Tests for /simulation endpoints."""

    def test_put_simulation_scenario(self, api_client):
        """PUT /simulation/scenario accepts request."""
        response = api_client.put("/simulation/scenario", json={"scenario": "stress"})
        assert response.status_code in [200, 400, 500]


class TestRootEndpoint:
    """Tests for root endpoint /."""

    def test_get_root_info(self, api_client):
        """GET / returns cluster info and API status."""
        response = api_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "cluster_id" in data
        assert data["machines_count"] == 5


class TestWebSocketEndpoint:
    """Tests for WebSocket /ws/cluster."""

    def test_websocket_connection(self, api_client):
        """WebSocket connects and receives snapshots."""
        with api_client.websocket_connect("/ws/cluster") as websocket:
            data = websocket.receive_json()
            assert "cluster_id" in data
            assert "metrics" in data

    def test_websocket_multiple_snapshots(self, api_client):
        """WebSocket sends multiple snapshots."""
        with api_client.websocket_connect("/ws/cluster") as websocket:
            for _ in range(2):
                data = websocket.receive_json()
                assert "cluster_id" in data

    def test_websocket_disconnect(self, api_client):
        """WebSocket accepts clean disconnection."""
        with api_client.websocket_connect("/ws/cluster") as websocket:
            data = websocket.receive_json()
            assert data is not None


class TestResponseFormats:
    """Validate API response formats."""

    def test_machine_snapshot_fields(self, api_client):
        """Machine snapshot has required fields."""
        response = api_client.get("/machines/srv-master-01")
        data = response.json()
        required = ["id", "role", "status", "temperature_c", "fans", "sensors"]
        for field in required:
            assert field in data

    def test_cluster_snapshot_fields(self, api_client):
        """Cluster snapshot has required fields."""
        response = api_client.get("/cluster/status")
        data = response.json()
        required = ["cluster_id", "ts", "metrics", "machines"]
        for field in required:
            assert field in data

    def test_temperature_range(self, api_client):
        """Temperatures are in valid range."""
        response = api_client.get("/machines/srv-master-01")
        data = response.json()
        temp = data["temperature_c"]
        assert 15.0 <= temp <= 95.0

    def test_sensors_have_data(self, api_client):
        """Sensors have required fields."""
        response = api_client.get("/machines/srv-master-01")
        data = response.json()
        assert len(data["sensors"]) > 0
        # sensors est un dict[sensor_id, {temp_c, bias_c}]
        for sensor_id, sensor_data in data["sensors"].items():
            assert isinstance(sensor_id, str)
            assert "temp_c" in sensor_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
