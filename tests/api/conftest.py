"""Pytest fixtures for API integration tests."""

import httpx
import pytest

API_URL = "http://localhost:8000"


@pytest.fixture
def client() -> httpx.Client:
    """Create an HTTP client for testing."""
    return httpx.Client(base_url=API_URL, timeout=10.0)
