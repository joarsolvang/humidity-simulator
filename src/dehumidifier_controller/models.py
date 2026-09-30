from typing import Literal

from pydantic import BaseModel, Field

from humidity_simulator.models import EnergyForecastTimeSeries, SimulationResult
from humidity_simulator.models.api_models import SimulationRequest


class DehumidifierSpec(BaseModel):
    """Dehumidifier hardware specification (no schedule — that is derived from the baseline)."""

    name: str
    wattage: float = Field(gt=0)
    extraction_rate: float = Field(gt=0)
    extraction_rate_unit: Literal["g/h", "kg/h", "lb/h"]


class OptimisationRequest(SimulationRequest):
    """Extends the simulation request with the inputs specific to optimisation."""

    energy_forecast: EnergyForecastTimeSeries
    dehumidifier: DehumidifierSpec


class OptimisationResult(BaseModel):
    """Final accepted schedule and simulation result from a completed optimisation run."""

    schedule: list[int]
    objective: float
    simulation_result: SimulationResult
