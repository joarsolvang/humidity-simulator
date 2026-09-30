from __future__ import annotations

from fastapi import APIRouter

from dehumidifier_controller.models import OptimisationRequest, OptimisationResult
from dehumidifier_controller.tasks import run_optimisation, run_simulation
from humidity_simulator.models import SimulationResult
from humidity_simulator.models.api_models import SimulationRequest

optimisation_router = APIRouter(prefix="/optimisation", tags=["optimisation"])
simulation_router = APIRouter(prefix="/simulate", tags=["simulation"])


@simulation_router.post("", response_model=SimulationResult)
def simulate(request: SimulationRequest) -> SimulationResult:
    """Run a simulation and return the result."""
    return run_simulation(request)


@optimisation_router.post("", response_model=OptimisationResult)
def optimise(request: OptimisationRequest) -> OptimisationResult:
    """Run the greedy optimiser to completion and return the final accepted schedule."""
    return run_optimisation(request)
