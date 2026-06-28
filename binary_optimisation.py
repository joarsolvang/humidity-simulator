import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.core.problem import ElementwiseProblem
from pymoo.operators.crossover.pntx import TwoPointCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.operators.sampling.rnd import BinaryRandomSampling
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from agile_predict_api import AgilePredictClient
from humidity_simulator.models import Dehumidifier, EnergyForecastTimeSeries, HumiditySource
from humidity_simulator.models.humidity_source import AmbientConditions
from openmeteo_client.weather import OpenMeteoClient

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Simulation configuration ────────────────────────────────────────────────
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
TIMEZONE = "UTC"
TIME_RESOLUTION = pd.Timedelta("15min")
SIM_DAYS = 2
LATITUDE = 51.5
LONGITUDE = -0.1
STARTING_RELATIVE_HUMIDITY = 50.0

# ── Dehumidifier specification ───────────────────────────────────────────────
DEHUMIDIFIER_WATTAGE = 250.0
DEHUMIDIFIER_EXTRACTION_RATE = 400.0  # g/h

# ── Objective parameters ─────────────────────────────────────────────────────
# Pence added to the objective for every timestep where internal RH exceeds 60 %.
# This creates a trade-off between electricity spend and humidity discomfort.
HUMIDITY_PENALTY_PENCE = 5.0
RH_THRESHOLD = 60.0

# ── GA parameters ────────────────────────────────────────────────────────────
POP_SIZE = 50
N_GENERATIONS = 30
SEED = 42


# ── Scenario helpers (same as dehumidifier_optimisation.py) ─────────────────


def _build_scenario_df(start_date: pd.Timestamp, days: int, time_resolution: str) -> pd.DataFrame:
    end = start_date + pd.Timedelta(days=days) - pd.Timedelta(time_resolution)
    index = pd.date_range(start=start_date, end=end, freq=time_resolution)
    df = pd.DataFrame(index=index)
    df["is_weekday"] = df.index.dayofweek < 5  # type: ignore[union-attr]
    df["hour"] = df.index.hour  # type: ignore[union-attr]
    df["minute"] = df.index.minute  # type: ignore[union-attr]
    return df


def _series_to_source(series: pd.Series, name: str) -> HumiditySource:  # type: ignore[type-arg]
    non_null = series.dropna()
    return HumiditySource(
        name=name,
        max_emissions_rate_unit="g/h",
        timestamps=[ts.strftime(TIMESTAMP_FORMAT) for ts in non_null.index],
        timestamp_format=TIMESTAMP_FORMAT,
        timezone=TIMEZONE,
        values=non_null.tolist(),
        values_unit="g/h",
    )


def scenario_one_bed_flat(
    start_date: pd.Timestamp,
    days: int = SIM_DAYS,
    time_resolution: str = "15min",
) -> list[HumiditySource]:
    """1 Bed Flat: single occupant over the given number of days."""
    df = _build_scenario_df(start_date, days, time_resolution)

    flat_occupation = df["is_weekday"] | ((df["hour"] < 12) & ~df["is_weekday"])
    df["breathing"] = 0
    df.loc[flat_occupation, "breathing"] = 80.0

    weekday_shower = df["is_weekday"] & (df["hour"] == 7) & (df["minute"].isin([0, 15]))
    weekend_shower = ~df["is_weekday"] & (df["hour"] == 9) & (df["minute"].isin([0, 15]))
    df["shower"] = pd.NA
    df.loc[weekday_shower | weekend_shower, "shower"] = 200.0

    weekday_cooking = df["is_weekday"] & (df["hour"] >= 18) & (df["hour"] < 19)
    df["cooking"] = pd.NA
    df.loc[weekday_cooking, "cooking"] = 15.0

    return [
        _series_to_source(df["breathing"], "Breathing (1 person)"),
        _series_to_source(df["shower"], "Shower"),
        _series_to_source(df["cooking"], "Cooking (Dinner)"),
    ]


def fetch_ambient_conditions(
    latitude: float,
    longitude: float,
    *,
    past_days: int = 0,
    forecast_days: int = SIM_DAYS,
    timezone: str = "UTC",
) -> AmbientConditions:
    client = OpenMeteoClient()
    forecast = client.get_humidity_forecast(
        latitude=latitude,
        longitude=longitude,
        hourly=["relative_humidity_2m", "temperature_2m"],
        daily=None,
        past_days=past_days,
        forecast_days=forecast_days,
        timezone=timezone,
    )
    hourly = forecast.hourly
    if hourly is None or hourly.relative_humidity_2m is None or hourly.temperature_2m is None:
        msg = "Open-Meteo response missing required hourly data"
        raise ValueError(msg)
    return AmbientConditions(
        name="OpenMeteo",
        timestamps=[t.isoformat() for t in hourly.time],
        timestamp_format="ISO8601",
        timezone=timezone,
        relative_humidity=hourly.relative_humidity_2m,
        ambient_temperature=hourly.temperature_2m,
        ambient_temperature_unit="Celcius",
    )


# ── pymoo problem definition ─────────────────────────────────────────────────


class DehumidifierOptimisationProblem(ElementwiseProblem):
    """Binary optimisation problem: find the on/off schedule that minimises mean relative humidity.

    Decision variables
    ------------------
    x[t] ∈ {0, 1}  –  1 if the dehumidifier is on during timestep t, 0 otherwise.

    Objective
    ---------
    Minimise mean(relative_humidity) over the simulation horizon.
    """

    def __init__(
        self,
        simulator: InternalHumiditySimulator,
        humidity_sources: list[HumiditySource],
        external_ambient_conditions: AmbientConditions,
        schedule_timestamps: list[str],
        energy_forecast: EnergyForecastTimeSeries,
        starting_relative_humidity: float = STARTING_RELATIVE_HUMIDITY,
    ) -> None:
        self.simulator = simulator
        self.humidity_sources = humidity_sources
        self.external_ambient_conditions = external_ambient_conditions
        self.schedule_timestamps = schedule_timestamps
        self.energy_forecast = energy_forecast
        self.starting_relative_humidity = starting_relative_humidity

        n_timesteps = len(schedule_timestamps)
        super().__init__(n_var=n_timesteps, n_obj=1, xl=0, xu=1)

    def _evaluate(self, x: np.ndarray, out: dict, *args, **kwargs) -> None:  # type: ignore[override]
        binary_schedule = [int(round(float(v))) for v in x]

        dehumidifier = Dehumidifier(
            name="dehumidifier",
            wattage=DEHUMIDIFIER_WATTAGE,
            extraction_rate=DEHUMIDIFIER_EXTRACTION_RATE,
            extraction_rate_unit="g/h",
            timestamps=self.schedule_timestamps,
            timestamp_format=TIMESTAMP_FORMAT,
            timezone=TIMEZONE,
            values=binary_schedule,
        )

        result = self.simulator.simulate(
            starting_relative_humidity=self.starting_relative_humidity,
            humidity_sources=self.humidity_sources,
            external_ambient_conditions=self.external_ambient_conditions,
            dehumidifier=dehumidifier,
            energy_forecast=self.energy_forecast,
            time_resolution=TIME_RESOLUTION,
        )

        running_cost = sum(result.dehumidifier_running_cost_pence or [])
        overhumidity_penalty = HUMIDITY_PENALTY_PENCE * sum(1 for rh in result.relative_humidity if rh > RH_THRESHOLD)
        out["F"] = [running_cost + overhumidity_penalty]


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_date = pd.Timestamp.now(tz="UTC").normalize()

    print("Fetching ambient conditions from Open-Meteo...")
    external_ambient_conditions = fetch_ambient_conditions(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        past_days=0,
        forecast_days=SIM_DAYS,
        timezone="UTC",
    )

    humidity_sources = scenario_one_bed_flat(start_date=start_date.tz_localize(None), days=SIM_DAYS)

    simulator = InternalHumiditySimulator(
        surface_area=25,
        surface_area_unit="m2",
        ceiling_height=2.5,
        ceiling_height_unit="m",
        internal_temperature=20,
        internal_temperature_unit="c",
        air_changes_per_hour=0.1,
    )

    # Run a baseline simulation (no dehumidifier) to obtain the exact aligned time index.
    # The result timestamps are used as the dehumidifier schedule timestamps, guaranteeing
    # that every binary variable maps to exactly one simulation timestep.
    print("Running baseline simulation to determine time index...")
    baseline = simulator.simulate(
        starting_relative_humidity=STARTING_RELATIVE_HUMIDITY,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        time_resolution=TIME_RESOLUTION,
    )

    schedule_timestamps = [pd.Timestamp(ts).strftime(TIMESTAMP_FORMAT) for ts in baseline.timestamps]
    n_timesteps = len(schedule_timestamps)
    print(f"Simulation horizon: {n_timesteps} timesteps ({TIME_RESOLUTION} resolution, {SIM_DAYS} days)")
    print(f"Baseline mean relative humidity: {float(np.mean(baseline.relative_humidity)):.2f}%")

    print("Fetching Agile electricity price forecast...")
    agile_client = AgilePredictClient()
    agile_forecasts = agile_client.get_forecast(region="H", days=SIM_DAYS)
    energy_forecast = EnergyForecastTimeSeries.model_validate(agile_forecasts[0].to_timeseries().model_dump())

    # ── Formulate and solve ──────────────────────────────────────────────────
    problem = DehumidifierOptimisationProblem(
        simulator=simulator,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        schedule_timestamps=schedule_timestamps,
        energy_forecast=energy_forecast,
        starting_relative_humidity=STARTING_RELATIVE_HUMIDITY,
    )

    algorithm = GA(
        pop_size=POP_SIZE,
        sampling=BinaryRandomSampling(),
        crossover=TwoPointCrossover(),
        mutation=BitflipMutation(),
        eliminate_duplicates=True,
    )

    termination = get_termination("n_gen", N_GENERATIONS)

    print(f"\nStarting GA: {n_timesteps} binary vars, pop_size={POP_SIZE}, n_gen={N_GENERATIONS}")
    opt_start = datetime.now()

    res = minimize(
        problem,
        algorithm,
        termination,
        seed=SEED,
        verbose=True,
    )

    elapsed = datetime.now() - opt_start
    print(f"\nOptimisation completed in {elapsed}")

    best_schedule = [int(round(float(v))) for v in res.X]
    hours_on = sum(best_schedule) * TIME_RESOLUTION.total_seconds() / 3600

    # Re-run the best solution to collect full result statistics and plot
    best_dehumidifier = Dehumidifier(
        name="dehumidifier",
        wattage=DEHUMIDIFIER_WATTAGE,
        extraction_rate=DEHUMIDIFIER_EXTRACTION_RATE,
        extraction_rate_unit="g/h",
        timestamps=schedule_timestamps,
        timestamp_format=TIMESTAMP_FORMAT,
        timezone=TIMEZONE,
        values=best_schedule,
    )
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    best_result = simulator.simulate(
        starting_relative_humidity=STARTING_RELATIVE_HUMIDITY,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        dehumidifier=best_dehumidifier,
        energy_forecast=energy_forecast,
        time_resolution=TIME_RESOLUTION,
        plot_results=True,
        plot_name=f"ga_optimised_{timestamp_str}",
    )

    total_cost = sum(best_result.dehumidifier_running_cost_pence or [])
    n_above_60 = sum(1 for rh in best_result.relative_humidity if rh > RH_THRESHOLD)
    penalty = HUMIDITY_PENALTY_PENCE * n_above_60

    print(f"\nObjective value              : {float(res.F[0]):.2f} p")
    print(f"  Electricity running cost   : {total_cost:.2f} p")
    print(f"  Humidity penalty           : {penalty:.2f} p  ({n_above_60} timesteps > {RH_THRESHOLD:.0f}%)")
    print(f"Dehumidifier on             : {sum(best_schedule)}/{n_timesteps} timesteps ({hours_on:.1f} h)")
    print(f"Mean relative humidity       : {float(np.mean(best_result.relative_humidity)):.2f}%")
    print(f"Plot saved to outputs/ga_optimised_{timestamp_str}.png")
