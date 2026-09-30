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

    def test_simulate_returns_expected_fields(self, client: httpx.Client) -> None:
        request_data = {
            "surface_area": 50,
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "air_changes_per_hour": 0.5,
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
            "external_ambient_conditions": {
                "name": "mock",
                "timestamps": ["2024-01-01 07:00", "2024-01-01 07:30"],
                "timestamp_format": "%Y-%m-%d %H:%M",
                "timezone": "UTC",
                "relative_humidity": [60.0, 60.0],
                "ambient_temperature": [10.0, 10.0],
                "ambient_temperature_unit": "Celcius",
            },
        }
        response = client.post("/simulate", json=request_data)
        assert response.status_code == 200

        result = response.json()
        assert "timestamps" in result
        assert "relative_humidity" in result
        assert "absolute_humidity" in result
        assert len(result["timestamps"]) == len(result["relative_humidity"])
        assert len(result["timestamps"]) == len(result["absolute_humidity"])

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
            "air_changes_per_hour": 0.5,
            "starting_relative_humidity": 50,
            "sources": [],
            "external_ambient_conditions": {
                "name": "mock",
                "timestamps": ["2024-01-01 07:00", "2024-01-01 07:30"],
                "timestamp_format": "%Y-%m-%d %H:%M",
                "timezone": "UTC",
                "relative_humidity": [60.0, 60.0],
                "ambient_temperature": [10.0, 10.0],
                "ambient_temperature_unit": "Celcius",
            },
        }
        response = client.post("/simulate", json=request_data)
        assert response.status_code == 200

        result = response.json()
        assert result["timestamps"] == []
        assert result["relative_humidity"] == []
        assert result["absolute_humidity"] == []


class TestOptimisationEndpoint:
    """Tests for the /optimisation endpoint."""

    def test_optimise_returns_final_schedule(self, client: httpx.Client) -> None:
        timestamps = ["2024-01-01 07:00", "2024-01-01 07:30", "2024-01-01 08:00"]
        request_data = {
            "surface_area": 50,
            "surface_area_unit": "m2",
            "ceiling_height": 2.5,
            "ceiling_height_unit": "m",
            "internal_temperature": 20,
            "internal_temperature_unit": "c",
            "air_changes_per_hour": 0.5,
            "starting_relative_humidity": 50,
            "time_resolution_minutes": 30,
            "sources": [
                {
                    "name": "shower",
                    "timestamps": timestamps,
                    "timestamp_format": "%Y-%m-%d %H:%M",
                    "timezone": "UTC",
                    "values": [0, 400, 0],
                    "values_unit": "g/h",
                    "max_emissions_rate_unit": "g/h",
                }
            ],
            "external_ambient_conditions": {
                "name": "mock",
                "timestamps": timestamps,
                "timestamp_format": "%Y-%m-%d %H:%M",
                "timezone": "UTC",
                "relative_humidity": [60.0, 60.0, 60.0],
                "ambient_temperature": [10.0, 10.0, 10.0],
                "ambient_temperature_unit": "Celcius",
            },
            "energy_forecast": {
                "timestamps": timestamps,
                "timestamp_format": "%Y-%m-%d %H:%M",
                "timezone": "UTC",
                "values": [15.0, 20.0, 12.0],
                "values_unit": "p/kWh",
            },
            "dehumidifier": {
                "name": "Dehumidifier",
                "wattage": 250.0,
                "extraction_rate": 400.0,
                "extraction_rate_unit": "g/h",
            },
        }
        response = client.post("/optimisation", json=request_data)
        assert response.status_code == 200

        result = response.json()
        assert len(result["schedule"]) == len(timestamps)
        assert all(v in (0, 1) for v in result["schedule"])
        assert isinstance(result["objective"], float)
        assert len(result["simulation_result"]["timestamps"]) == len(timestamps)
