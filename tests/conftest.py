import pytest

from humidity_simulator.engine.simulator import InternalHumiditySimulator


@pytest.fixture
def simulator() -> InternalHumiditySimulator:
    """Create a standard simulator instance for testing."""
    return InternalHumiditySimulator(
        surface_area=100,
        surface_area_unit="m2",
        ceiling_height=3,
        ceiling_height_unit="m",
        internal_temperature=20,
        internal_temperature_unit="c",
    )
