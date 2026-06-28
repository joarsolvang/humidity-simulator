from __future__ import annotations

import os
from typing import Annotated, Literal

import redis
from fastapi import APIRouter, HTTPException, Query

from dehumidifier_controller.greedy_optimisation import GreedyStep
from dehumidifier_controller.models import (
    JobCreated,
    JobStatus,
    OptimisationRequest,
    SimulationJobResult,
    StepsResponse,
)
from dehumidifier_controller.tasks import run_optimisation, run_simulation
from humidity_simulator.models import SimulationResult
from humidity_simulator.models.api_models import SimulationRequest

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

optimisation_router = APIRouter(prefix="/optimisation", tags=["optimisation"])
simulation_router = APIRouter(prefix="/simulate", tags=["simulation"])


def _get_redis() -> redis.Redis:  # type: ignore[type-arg]
    return redis.from_url(REDIS_URL)


@simulation_router.post("/jobs", response_model=JobCreated, status_code=202)
def submit_simulation(request: SimulationRequest) -> JobCreated:
    """Submit a simulation job. Returns a job ID for polling."""
    task = run_simulation.delay(request.model_dump(mode="json"))
    return JobCreated(job_id=task.id)


@simulation_router.get("/jobs/{job_id}/result", response_model=SimulationJobResult)
def get_simulation_result(job_id: str) -> SimulationJobResult:
    """Poll for the simulation result. `result` is null while the job is still running."""
    r = _get_redis()

    status_raw = r.get(f"job:{job_id}:status")
    if status_raw is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found or expired")

    status: Literal["running", "complete", "error"] = status_raw.decode()  # type: ignore[assignment,union-attr]

    result: SimulationResult | None = None
    if status == "complete":
        result_raw = r.get(f"job:{job_id}:result")
        if result_raw is not None:
            result = SimulationResult.model_validate_json(result_raw)  # type: ignore[union-attr,arg-type]

    error: str | None = None
    if status == "error":
        error_raw = r.get(f"job:{job_id}:error")
        error = error_raw.decode() if error_raw else "Unknown error"  # type: ignore[union-attr]

    return SimulationJobResult(job_id=job_id, status=status, result=result, error=error)


@optimisation_router.post("/jobs", response_model=JobCreated, status_code=202)
def submit_optimisation(request: OptimisationRequest) -> JobCreated:
    """Submit a greedy optimisation job. Returns a job ID for polling."""
    task = run_optimisation.delay(request.model_dump(mode="json"))
    return JobCreated(job_id=task.id)


@optimisation_router.get("/jobs/{job_id}/steps", response_model=StepsResponse)
def get_steps(
    job_id: str,
    from_index: Annotated[int, Query(ge=0, description="Return steps from this index onwards")] = 0,
) -> StepsResponse:
    """Poll for new optimisation steps since the last seen index."""
    r = _get_redis()

    status_raw = r.get(f"job:{job_id}:status")
    if status_raw is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found or expired")

    status: str = status_raw.decode()  # type: ignore[union-attr]
    raw_steps: list[bytes] = r.lrange(f"job:{job_id}:steps", from_index, -1)  # type: ignore[assignment]
    steps = [GreedyStep.model_validate_json(s) for s in raw_steps]

    error: str | None = None
    if status == "error":
        error_raw = r.get(f"job:{job_id}:error")
        error = error_raw.decode() if error_raw else "Unknown error"  # type: ignore[union-attr]

    return StepsResponse(
        job_id=job_id,
        steps=steps,
        complete=status in {"complete", "error"},
        error=error,
    )


@optimisation_router.get("/jobs/{job_id}/status", response_model=JobStatus)
def get_job_status(job_id: str) -> JobStatus:
    """Return the current status and total step count for an optimisation job."""
    r = _get_redis()

    status_raw = r.get(f"job:{job_id}:status")
    if status_raw is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found or expired")

    return JobStatus(
        job_id=job_id,
        status=status_raw.decode(),  # type: ignore[union-attr]
        total_steps=int(r.llen(f"job:{job_id}:steps")),  # type: ignore[arg-type]
    )
