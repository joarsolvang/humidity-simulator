from typing import Literal

from pydantic import BaseModel, Field

from dehumidifier_controller.greedy_optimisation import GreedyStep
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


class JobCreated(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["running", "complete", "error"]
    total_steps: int


class SimulationJobResult(BaseModel):
    job_id: str
    status: Literal["running", "complete", "error"]
    result: SimulationResult | None = None
    error: str | None = None


class StepsResponse(BaseModel):
    job_id: str
    steps: list[GreedyStep]
    complete: bool
    error: str | None = None
