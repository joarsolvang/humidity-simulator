import pytest

from humidity_simulator.engine.simulator import InternalHumiditySimulator, UnitConsistencyError


class TestUnitValidation:
    """Tests for unit consistency validation."""

    def test_valid_metric_units(self) -> None:
        """Simulator accepts all metric units."""
        sim = InternalHumiditySimulator(
            surface_area=100,
            surface_area_unit="m2",
            ceiling_height=3,
            ceiling_height_unit="m",
            internal_temperature=20,
            internal_temperature_unit="c",
        )
        assert sim.surface_area == 100
        assert sim.ceiling_height == 3
        assert sim.internal_temperature == 20

    def test_valid_metric_units_kelvin(self) -> None:
        """Simulator accepts metric units with Kelvin temperature."""
        sim = InternalHumiditySimulator(
            surface_area=100,
            surface_area_unit="m2",
            ceiling_height=3,
            ceiling_height_unit="m",
            internal_temperature=293,
            internal_temperature_unit="k",
        )
        assert sim.internal_temperature_unit == "k"

    def test_valid_imperial_units(self) -> None:
        """Simulator accepts all imperial units."""
        sim = InternalHumiditySimulator(
            surface_area=1000,
            surface_area_unit="ft2",
            ceiling_height=10,
            ceiling_height_unit="ft",
            internal_temperature=68,
            internal_temperature_unit="f",
        )
        assert sim.surface_area == 1000
        assert sim.ceiling_height == 10
        assert sim.internal_temperature == 68

    def test_mixed_area_metric_height_imperial_raises(self) -> None:
        """Mixing metric area with imperial height raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=100,
                surface_area_unit="m2",
                ceiling_height=10,
                ceiling_height_unit="ft",
                internal_temperature=20,
                internal_temperature_unit="c",
            )

    def test_mixed_area_imperial_height_metric_raises(self) -> None:
        """Mixing imperial area with metric height raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=1000,
                surface_area_unit="ft2",
                ceiling_height=3,
                ceiling_height_unit="m",
                internal_temperature=68,
                internal_temperature_unit="f",
            )

    def test_mixed_metric_dimensions_imperial_temperature_raises(self) -> None:
        """Mixing metric dimensions with imperial temperature raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=100,
                surface_area_unit="m2",
                ceiling_height=3,
                ceiling_height_unit="m",
                internal_temperature=68,
                internal_temperature_unit="f",
            )

    def test_mixed_imperial_dimensions_metric_temperature_raises(self) -> None:
        """Mixing imperial dimensions with metric temperature raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=1000,
                surface_area_unit="ft2",
                ceiling_height=10,
                ceiling_height_unit="ft",
                internal_temperature=20,
                internal_temperature_unit="c",
            )

    def test_error_message_contains_unit_details(self) -> None:
        """Error message includes which units are metric vs imperial."""
        with pytest.raises(UnitConsistencyError) as exc_info:
            InternalHumiditySimulator(
                surface_area=100,
                surface_area_unit="m2",
                ceiling_height=10,
                ceiling_height_unit="ft",
                internal_temperature=20,
                internal_temperature_unit="c",
            )
        error_message = str(exc_info.value)
        assert "surface_area_unit=metric" in error_message
        assert "ceiling_height_unit=imperial" in error_message
        assert "temperature_unit=metric" in error_message
