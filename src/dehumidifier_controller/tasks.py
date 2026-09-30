from __future__ import annotations

import logging

import pandas as pd

from dehumidifier_controller.greedy_optimisation import greedy_optimiser
from dehumidifier_controller.models import OptimisationRequest, OptimisationResult
from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import Dehumidifier, EnergyForecastTimeSeries, SimulationResult
from humidity_simulator.models.api_models import SimulationRequest

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
_TIMEZONE = "UTC"


def _align_prices(
    energy_forecast: EnergyForecastTimeSeries,
    schedule_timestamps: list[str],
    time_resolution: pd.Timedelta,
) -> list[float]:
    """Forward-fill energy prices onto the simulation time grid."""
    price_fmt = (
        "ISO8601"
        if energy_forecast.timestamp_format.replace(" ", "") == "ISO8601"
        else energy_forecast.timestamp_format
    )
    price_ts = pd.to_datetime(energy_forecast.timestamps, format=price_fmt)
    if price_ts.tz is None:
        price_ts = price_ts.tz_localize(energy_forecast.timezone)
    price_series = pd.Series(energy_forecast.values, index=price_ts).resample(time_resolution).ffill()
    schedule_index = pd.to_datetime(schedule_timestamps, format=_TIMESTAMP_FORMAT).tz_localize(_TIMEZONE)
    return price_series.reindex(schedule_index, method="ffill").fillna(0.0).tolist()


def _build_simulator(request: SimulationRequest) -> InternalHumiditySimulator:
    return InternalHumiditySimulator(
        surface_area=request.surface_area,
        surface_area_unit=request.surface_area_unit,
        ceiling_height=request.ceiling_height,
        ceiling_height_unit=request.ceiling_height_unit,
        internal_temperature=request.internal_temperature,
        internal_temperature_unit=request.internal_temperature_unit,
        air_changes_per_hour=request.air_changes_per_hour,
    )


def _setup_optimisation(
    request: OptimisationRequest,
) -> tuple[InternalHumiditySimulator, list[float], Dehumidifier, pd.Timedelta]:
    """Build all inputs needed by the greedy optimiser from the request."""
    time_resolution = pd.Timedelta(minutes=request.time_resolution_minutes)

    simulator = _build_simulator(request)

    baseline = simulator.simulate(
        starting_relative_humidity=request.starting_relative_humidity,
        humidity_sources=request.sources,
        external_ambient_conditions=request.external_ambient_conditions,
        time_resolution=time_resolution,
    )
    schedule_timestamps = [pd.Timestamp(ts).strftime(_TIMESTAMP_FORMAT) for ts in baseline.timestamps]
    n = len(schedule_timestamps)

    aligned_prices = _align_prices(request.energy_forecast, schedule_timestamps, time_resolution)

    dehumidifier_template = Dehumidifier(
        name=request.dehumidifier.name,
        wattage=request.dehumidifier.wattage,
        extraction_rate=request.dehumidifier.extraction_rate,
        extraction_rate_unit=request.dehumidifier.extraction_rate_unit,
        timestamps=schedule_timestamps,
        timestamp_format=_TIMESTAMP_FORMAT,
        timezone=_TIMEZONE,
        values=[1] * n,
    )

    return simulator, aligned_prices, dehumidifier_template, time_resolution


def run_optimisation(request: OptimisationRequest) -> OptimisationResult:
    """Run the greedy optimiser to completion and return the final accepted schedule."""
    logger.info("Starting optimisation")

    simulator, aligned_prices, dehumidifier_template, time_resolution = _setup_optimisation(request)

    final_step = None
    for step in greedy_optimiser(
        simulator=simulator,
        aligned_prices=aligned_prices,
        humidity_sources=request.sources,
        external_ambient_conditions=request.external_ambient_conditions,
        energy_forecast=request.energy_forecast,
        dehumidifier_template=dehumidifier_template,
        starting_relative_humidity=request.starting_relative_humidity,
        time_resolution=time_resolution,
    ):
        final_step = step

    if final_step is None:
        msg = "Optimisation produced no steps (empty schedule)"
        raise ValueError(msg)

    logger.info("Completed optimisation")
    return OptimisationResult(
        schedule=final_step.schedule,
        objective=final_step.objective,
        simulation_result=final_step.simulation_result,
    )


def run_simulation(request: SimulationRequest) -> SimulationResult:
    """Run a single simulation and return the result."""
    logger.info("Starting simulation")

    time_resolution = pd.Timedelta(minutes=request.time_resolution_minutes)
    simulator = _build_simulator(request)

    result = simulator.simulate(
        starting_relative_humidity=request.starting_relative_humidity,
        humidity_sources=request.sources,
        external_ambient_conditions=request.external_ambient_conditions,
        time_resolution=time_resolution,
    )

    logger.info("Completed simulation")
    return result
