from typing import Literal

from humidity_simulator.models import HumiditySource

UnitSystem = Literal["metric", "imperial"]


class UnitConsistencyError(Exception):
    """Raised when input units are inconsistent."""


class InternalHumiditySimulator:
    """Simulator of internal humidity"""

    METRIC_UNITS = {"m2", "m", "c", "k"}
    IMPERIAL_UNITS = {"ft2", "ft", "f"}

    def __init__(
        self,
        surface_area: float | int,
        surface_area_unit: Literal["m2", "ft2"],
        ceiling_height: float | int,
        ceiling_height_unit: Literal["m", "ft"],
        internal_temperature: float | int,
        internal_temperature_unit: Literal["c", "k", "f"],
    ) -> None:
        self._validate_unit_consistency(surface_area_unit, ceiling_height_unit, internal_temperature_unit)

        self.surface_area = surface_area
        self.surface_area_unit = surface_area_unit
        self.ceiling_height = ceiling_height
        self.ceiling_height_unit = ceiling_height_unit
        self.internal_temperature = internal_temperature
        self.internal_temperature_unit = internal_temperature_unit
        self.environment_volume = self.surface_area * self.ceiling_height

    def simulate(
        self,
        starting_humidity: float | int,
        humidity_sources: list[HumiditySource],
    ) -> None:
        """Run the humidity simulation."""
        ...

    def _get_unit_system(self, unit: str) -> UnitSystem:
        """Determine whether a unit belongs to metric or imperial system."""
        if unit in self.METRIC_UNITS:
            return "metric"
        if unit in self.IMPERIAL_UNITS:
            return "imperial"
        msg = f"Unknown unit: {unit}"
        raise ValueError(msg)

    def _validate_unit_consistency(
        self,
        surface_area_unit: str,
        ceiling_height_unit: str,
        temperature_unit: str,
    ) -> None:
        """Validate that all input units belong to the same unit system.

        Raises:
            UnitConsistencyError: If units are from mixed systems (metric and imperial).
        """
        units = {
            "surface_area_unit": surface_area_unit,
            "ceiling_height_unit": ceiling_height_unit,
            "temperature_unit": temperature_unit,
        }

        systems = {name: self._get_unit_system(unit) for name, unit in units.items()}
        unique_systems = set(systems.values())

        if len(unique_systems) > 1:
            details = ", ".join(f"{name}={system}" for name, system in systems.items())
            msg = f"Inconsistent unit systems: {details}. All units must be metric or imperial."
            raise UnitConsistencyError(msg)

