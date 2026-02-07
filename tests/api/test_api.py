"""Integration tests for the humidity simulation API.

These tests run against a Docker container managed by conftest.py fixtures.
"""

import httpx


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_200(self, client: httpx.Client) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_healthy_status(self, client: httpx.Client) -> None:
        response = client.get("/health")
        assert response.json() == {"status": "healthy"}


class TestSimulateEndpoint:
    """Tests for the /simulate endpoint."""

    def test_simulate_returns_200(self, client: httpx.Client) -> None:
        request_data = {
            "surface_area": 50,
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "starting_relative_humidity": 50,
            "time_resolution_minutes": 30,
            "sources": [
                {
                    "name": "shower",
                    "timestamps": ["2024-01-01 07:00", "2024-01-01 07:30"],
                    "timestamp_format": "%Y-%m-%d %H:%M",
                    "timezone": "UTC",
                    "values": [0, 400],
                    "values_unit": "g/h",
                    "max_emissions_rate_unit": "g/h",
                }
            ],
        }
        response = client.post("/simulate", json=request_data)
        assert response.status_code == 200

    def test_simulate_returns_expected_fields(self, client: httpx.Client) -> None:
        request_data = {
            "surface_area": 50,
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "starting_relative_humidity": 50,
            "time_resolution_minutes": 30,
            "sources": [
                {
                    "name": "shower",
                    "timestamps": ["2024-01-01 07:00", "2024-01-01 07:30"],
                    "timestamp_format": "%Y-%m-%d %H:%M",
                    "timezone": "UTC",
                    "values": [0, 400],
                    "values_unit": "g/h",
                    "max_emissions_rate_unit": "g/h",
                }
            ],
        }
        response = client.post("/simulate", json=request_data)
        data = response.json()

        assert "timestamps" in data
        assert "relative_humidity" in data
        assert "absolute_humidity" in data
        assert len(data["timestamps"]) == len(data["relative_humidity"])
        assert len(data["timestamps"]) == len(data["absolute_humidity"])

    def test_simulate_validates_surface_area(self, client: httpx.Client) -> None:
        request_data = {
            "surface_area": -10,  # Invalid: must be > 0
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "starting_relative_humidity": 50,
            "sources": [],
        }
        response = client.post("/simulate", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_simulate_validates_humidity_range(self, client: httpx.Client) -> None:
        request_data = {
            "surface_area": 50,
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "starting_relative_humidity": 150,  # Invalid: must be <= 100
            "sources": [],
        }
        response = client.post("/simulate", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_simulate_with_empty_sources(self, client: httpx.Client) -> None:
        request_data = {
            "surface_area": 50,
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "starting_relative_humidity": 50,
            "sources": [],
        }
        response = client.post("/simulate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["timestamps"] == []
        assert data["relative_humidity"] == []
        assert data["absolute_humidity"] == []
