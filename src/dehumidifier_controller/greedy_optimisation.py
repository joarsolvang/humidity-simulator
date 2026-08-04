from __future__ import annotations

import logging
from collections.abc import Generator

import pandas as pd
from pydantic import BaseModel

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import Dehumidifier, EnergyForecastTimeSeries, HumiditySource
from humidity_simulator.models.humidity_source import AmbientConditions
from humidity_simulator.models.simulation_result import SimulationResult

logger = logging.getLogger(__name__)

HUMIDITY_PENALTY_PENCE = 20.0
RH_THRESHOLD = 60.0


class GreedyStep(BaseModel):
    """State snapshot yielded after each attempted turn-off."""

    iteration: int
    n_total: int
    schedule: list[int]
    objective: float
    simulation_result: SimulationResult
    accepted: bool


def _objective(result: SimulationResult) -> float:
    running_cost = sum(result.dehumidifier_running_cost_pence or [])
    penalty = HUMIDITY_PENALTY_PENCE * sum(max(0, rh - RH_THRESHOLD) for rh in result.relative_humidity)
    return running_cost + penalty


def _simulate(
    simulator: InternalHumiditySimulator,
    schedule: list[int],
    dehumidifier_template: Dehumidifier,
    humidity_sources: list[HumiditySource],
    external_ambient_conditions: AmbientConditions,
    energy_forecast: EnergyForecastTimeSeries,
    starting_relative_humidity: float,
    time_resolution: pd.Timedelta,
) -> SimulationResult:
    dehumidifier = dehumidifier_template.model_copy(update={"values": schedule})
    return simulator.simulate(
        starting_relative_humidity=starting_relative_humidity,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        dehumidifier=dehumidifier,
        energy_forecast=energy_forecast,
        time_resolution=time_resolution,
    )


def greedy_optimiser(
    simulator: InternalHumiditySimulator,
    aligned_prices: list[float],
    humidity_sources: list[HumiditySource],
    external_ambient_conditions: AmbientConditions,
    energy_forecast: EnergyForecastTimeSeries,
    dehumidifier_template: Dehumidifier,
    starting_relative_humidity: float,
    time_resolution: pd.Timedelta,
) -> Generator[GreedyStep, None, None]:
    """Greedy dehumidifier schedule optimiser.

    Starts with all timesteps ON, then greedily turns off the most expensive timestep
    at each step, accepting the change only when it does not increase the objective
    (electricity cost + humidity-over-threshold penalty).

    Yields a GreedyStep after each attempted turn-off so the caller can update a UI
    without coupling the algorithm to any specific display logic.
    """
    n = len(dehumidifier_template.timestamps)
    schedule = [1] * n

    current_result = _simulate(
        simulator,
        schedule,
        dehumidifier_template,
        humidity_sources,
        external_ambient_conditions,
        energy_forecast,
        starting_relative_humidity,
        time_resolution,
    )
    current_obj = _objective(current_result)
    logger.info(f"Greedy optimiser: {n} timesteps, initial objective = {current_obj:.2f} p")

    sorted_indices = sorted(range(n), key=lambda i: aligned_prices[i], reverse=True)

    for iteration, idx in enumerate(sorted_indices):
        logger.debug(f"Step {iteration + 1}/{n}: timestep {idx} at {aligned_prices[idx]:.4f} p/kWh")

        schedule[idx] = 0
        candidate_result = _simulate(
            simulator,
            schedule,
            dehumidifier_template,
            humidity_sources,
            external_ambient_conditions,
            energy_forecast,
            starting_relative_humidity,
            time_resolution,
        )
        candidate_obj = _objective(candidate_result)

        if candidate_obj <= current_obj:
            current_obj = candidate_obj
            current_result = candidate_result
            accepted = True
            logger.debug(f"  Accepted: objective = {current_obj:.2f} p")
        else:
            schedule[idx] = 1
            accepted = False
            logger.debug(f"  Rejected: would increase to {candidate_obj:.2f} p")

        yield GreedyStep(
            iteration=iteration,
            n_total=n,
            schedule=list(schedule),
            objective=current_obj,
            simulation_result=current_result,
            accepted=accepted,
        )
