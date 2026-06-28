import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from agile_predict_api import AgilePredictClient
from dehumidifier_controller.greedy_optimisation import GreedyStep, greedy_optimiser
from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import Dehumidifier, EnergyForecastTimeSeries, HumiditySource
from humidity_simulator.models.humidity_source import AmbientConditions
from openmeteo_client.weather import OpenMeteoClient

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
TIMEZONE = "UTC"
TIME_RESOLUTION = pd.Timedelta("15min")
SIM_DAYS = 2
LATITUDE = 51.5
LONGITUDE = -0.1
STARTING_RELATIVE_HUMIDITY = 50.0
DEHUMIDIFIER_WATTAGE = 250.0
DEHUMIDIFIER_EXTRACTION_RATE = 400.0
OUTPUT_DIR = Path("outputs")


def _build_scenario_df(start_date: pd.Timestamp) -> pd.DataFrame:
    end = start_date + pd.Timedelta(days=SIM_DAYS) - TIME_RESOLUTION
    index = pd.date_range(start=start_date, end=end, freq=TIME_RESOLUTION)
    df = pd.DataFrame(index=index)
    df["is_weekday"] = df.index.dayofweek < 5
    df["hour"] = df.index.hour
    df["minute"] = df.index.minute
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


def scenario_one_bed_flat(start_date: pd.Timestamp) -> list[HumiditySource]:
    df = _build_scenario_df(start_date)

    flat_occupation = df["is_weekday"] | ((df["hour"] < 12) & ~df["is_weekday"])
    df["breathing"] = 0.0
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


def fetch_ambient_conditions(latitude: float, longitude: float) -> AmbientConditions:
    client = OpenMeteoClient()
    forecast = client.get_humidity_forecast(
        latitude=latitude,
        longitude=longitude,
        hourly=["relative_humidity_2m", "temperature_2m"],
        daily=None,
        past_days=0,
        forecast_days=SIM_DAYS,
        timezone="UTC",
    )
    hourly = forecast.hourly
    return AmbientConditions(
        name="OpenMeteo",
        timestamps=[t.isoformat() for t in hourly.time],
        timestamp_format="ISO8601",
        timezone="UTC",
        relative_humidity=hourly.relative_humidity_2m,
        ambient_temperature=hourly.temperature_2m,
        ambient_temperature_unit="Celcius",
    )


def save_plot(step: GreedyStep, output_dir: Path) -> None:
    timestamps = pd.to_datetime(step.simulation_result.timestamps)
    rh = step.simulation_result.relative_humidity
    schedule = step.schedule
    delta = timestamps[1] - timestamps[0]

    fig, (ax_rh, ax_sched) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)

    # ── Relative humidity ────────────────────────────────────────────────────
    ax_rh.plot(timestamps, rh, color="steelblue", linewidth=2, label="Internal RH (%)")
    ax_rh.axhline(y=60, color="orange", linestyle="--", linewidth=1, alpha=0.8, label="60 % recommended max")
    ax_rh.axhline(y=40, color="green", linestyle="--", linewidth=1, alpha=0.8, label="40 % recommended min")
    ax_rh.set_ylabel("Relative Humidity (%)")
    ax_rh.set_ylim(0, 105)
    ax_rh.grid(alpha=0.3)

    # ── Dehumidifier schedule ────────────────────────────────────────────────
    ax_sched.step(timestamps, schedule, where="post", color="green", linewidth=1.5)
    ax_sched.fill_between(timestamps, schedule, step="post", color="green", alpha=0.3)
    ax_sched.set_ylabel("Dehumidifier")
    ax_sched.set_yticks([0, 1])
    ax_sched.set_yticklabels(["Off", "On"])
    ax_sched.set_ylim(-0.1, 1.4)
    ax_sched.set_xlabel("Time")
    ax_sched.grid(alpha=0.3)

    # ── Green shading on the RH panel for ON periods ─────────────────────────
    labeled = False
    i, n = 0, len(schedule)
    while i < n:
        if schedule[i] == 1:
            j = i
            while j < n and schedule[j] == 1:
                j += 1
            ax_rh.axvspan(
                timestamps[i],
                timestamps[j - 1] + delta,
                alpha=0.15,
                color="green",
                label="Dehumidifier on" if not labeled else None,
            )
            labeled = True
            i = j
        else:
            i += 1

    ax_rh.legend(loc="upper right")

    n_off = sum(1 - v for v in schedule)
    fig.suptitle(
        f"Greedy optimisation — iter {step.iteration}  |  "
        f"{n_off}/{step.n_total} timesteps off  |  "
        f"objective {step.objective:.2f} p"
    )
    plt.xticks(rotation=45)
    plt.tight_layout()

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"greedy_iter_{step.iteration}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


if __name__ == "__main__":
    start_date = pd.Timestamp.now(tz="UTC").normalize()

    print("Fetching ambient conditions...")
    external_ambient_conditions = fetch_ambient_conditions(LATITUDE, LONGITUDE)

    humidity_sources = scenario_one_bed_flat(start_date.tz_localize(None))

    simulator = InternalHumiditySimulator(
        surface_area=25,
        surface_area_unit="m2",
        ceiling_height=2.5,
        ceiling_height_unit="m",
        internal_temperature=20,
        internal_temperature_unit="c",
        air_changes_per_hour=0.1,
    )

    print("Running baseline simulation to fix time grid...")
    baseline = simulator.simulate(
        starting_relative_humidity=STARTING_RELATIVE_HUMIDITY,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        time_resolution=TIME_RESOLUTION,
    )
    schedule_timestamps = [pd.Timestamp(ts).strftime(TIMESTAMP_FORMAT) for ts in baseline.timestamps]
    n = len(schedule_timestamps)
    print(f"  {n} timesteps ({TIME_RESOLUTION} resolution, {SIM_DAYS} days)")

    print("Fetching Agile electricity prices...")
    agile_client = AgilePredictClient()
    agile_forecasts = agile_client.get_forecast(region="H", days=SIM_DAYS)
    energy_forecast = EnergyForecastTimeSeries.model_validate(agile_forecasts[0].to_timeseries().model_dump())

    price_fmt = (
        "ISO8601"
        if energy_forecast.timestamp_format.replace(" ", "") == "ISO8601"
        else energy_forecast.timestamp_format
    )
    price_ts = pd.to_datetime(energy_forecast.timestamps, format=price_fmt)
    if price_ts.tz is None:
        price_ts = price_ts.tz_localize(energy_forecast.timezone)
    price_series = pd.Series(energy_forecast.values, index=price_ts).resample(TIME_RESOLUTION).ffill()
    schedule_ts_index = pd.to_datetime(schedule_timestamps, format=TIMESTAMP_FORMAT).tz_localize(TIMEZONE)
    aligned_prices = price_series.reindex(schedule_ts_index, method="ffill").fillna(0.0).tolist()

    dehumidifier_template = Dehumidifier(
        name="dehumidifier",
        wattage=DEHUMIDIFIER_WATTAGE,
        extraction_rate=DEHUMIDIFIER_EXTRACTION_RATE,
        extraction_rate_unit="g/h",
        timestamps=schedule_timestamps,
        timestamp_format=TIMESTAMP_FORMAT,
        timezone=TIMEZONE,
        values=[1] * n,
    )

    print("Running greedy optimisation...")
    for step in greedy_optimiser(
        simulator=simulator,
        aligned_prices=aligned_prices,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        energy_forecast=energy_forecast,
        dehumidifier_template=dehumidifier_template,
        starting_relative_humidity=STARTING_RELATIVE_HUMIDITY,
        time_resolution=TIME_RESOLUTION,
    ):
        status = "accepted" if step.accepted else "rejected"
        print(f"  iter {step.iteration:>3}/{step.n_total}  {status}  objective {step.objective:.2f} p")
        if step.accepted:
            save_plot(step, OUTPUT_DIR)
