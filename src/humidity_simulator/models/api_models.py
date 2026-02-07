"""Pydantic models for the humidity simulation API."""

from typing import Literal

from pydantic import BaseModel, Field

from humidity_simulator.models.humidity_source import HumiditySource


class SimulationRequest(BaseModel):
    """Request body for the /simulate endpoint."""

    # Room configuration
    surface_area: float = Field(gt=0, description="Floor area of the room")
    surface_area_unit: Literal["m2", "ft2"] = Field(description="Unit for surface area")
    ceiling_height: float = Field(gt=0, description="Height of the ceiling")
    ceiling_height_unit: Literal["m", "ft"] = Field(description="Unit for ceiling height")
    internal_temperature: float = Field(description="Room temperature")
    internal_temperature_unit: Literal["c", "k", "f"] = Field(
        description="Unit for temperature (Celsius, Kelvin, Fahrenheit)"
    )

    # Simulation parameters
    starting_relative_humidity: float = Field(ge=0, le=100, description="Initial relative humidity (0-100%)")
    time_resolution_minutes: int = Field(default=30, gt=0, description="Time step for simulation in minutes")

    # Humidity sources - reuses the existing HumiditySource model
    sources: list[HumiditySource] = Field(description="List of humidity sources to simulate")
