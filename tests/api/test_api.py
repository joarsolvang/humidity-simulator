"""Integration tests for the humidity simulation API.

These tests run against a Docker container managed by conftest.py fixtures.
"""

import time

import httpx

_POLL_INTERVAL = 0.5
_POLL_TIMEOUT = 30.0


def _submit_and_await_result(client: httpx.Client, request_data: dict) -> dict:
    """Submit a simulation job and poll until it completes, returning the job result payload."""
    submit_response = client.post("/simulate/jobs", json=request_data)
    submit_response.raise_for_status()
    job_id = submit_response.json()["job_id"]

    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        result_response = client.get(f"/simulate/jobs/{job_id}/result")
        if result_response.status_code == 404:
            time.sleep(_POLL_INTERVAL)
            continue
        result_response.raise_for_status()
        data = result_response.json()
        if data["status"] in ("complete", "error"):
            return data
        time.sleep(_POLL_INTERVAL)

    raise TimeoutError(f"Simulation job {job_id!r} did not complete within {_POLL_TIMEOUT}s")


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_200(self, client: httpx.Client) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_healthy_status(self, client: httpx.Client) -> None:
        response = client.get("/health")
        assert response.json() == {"status": "healthy"}


class TestSimulateEndpoint:
    """Tests for the /simulate/jobs endpoint."""

    def test_simulate_returns_202(self, client: httpx.Client) -> None:
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
        response = client.post("/simulate/jobs", json=request_data)
        assert response.status_code == 202
        assert "job_id" in response.json()

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
        data = _submit_and_await_result(client, request_data)

        assert data["status"] == "complete"
        result = data["result"]
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
        response = client.post("/simulate/jobs", json=request_data)
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
        response = client.post("/simulate/jobs", json=request_data)
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
        data = _submit_and_await_result(client, request_data)

        assert data["status"] == "complete"
        result = data["result"]
        assert result["timestamps"] == []
        assert result["relative_humidity"] == []
        assert result["absolute_humidity"] == []
