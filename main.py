"""Example usage of the humidity simulator."""

import logging
import sys
from datetime import datetime

import pandas as pd
from agile_predict_api import AgilePredictClient
from openmeteo_client.weather import OpenMeteoClient

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import Dehumidifier, EnergyForecastTimeSeries, HumiditySource
from humidity_simulator.models.humidity_source import AmbientConditions

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# London coordinates — adjust for the target location
LATITUDE = 51.5
LONGITUDE = -0.1
DEFAULT_SIMULATION_DAYS = 14
DEFAULT_TIME_RESOLUTION = "15min"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
TIMEZONE = "UTC"


def _build_scenario_df(start_date: pd.Timestamp, days: int, time_resolution: str) -> pd.DataFrame:
    """Build a DataFrame with a datetime index and calendar metadata columns."""
    end = start_date + pd.Timedelta(days=days) - pd.Timedelta(time_resolution)
    index = pd.date_range(start=start_date, end=end, freq=time_resolution)
    df = pd.DataFrame(index=index)
    df["is_weekday"] = df.index.dayofweek < 5  # type: ignore[union-attr]
    df["hour"] = df.index.hour  # type: ignore[union-attr]
    df["minute"] = df.index.minute  # type: ignore[union-attr]
    return df


def _series_to_source(series: pd.Series, name: str) -> HumiditySource:  # type: ignore[type-arg]
    """Convert a non-null pandas Series into a HumiditySource."""
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
    days: int = DEFAULT_SIMULATION_DAYS,
    time_resolution: str = DEFAULT_TIME_RESOLUTION,
) -> list[HumiditySource]:
    """1 Bed Flat: single occupant over the given number of days.

    Weekdays (Mon-Fri): shower at 07:00, work from home, cook dinner.
    Weekends (Sat-Sun): shower at 09:00, no cooking.
    Breathing is constant throughout.
    """
    df = _build_scenario_df(start_date, days, time_resolution)

    flat_occupation = df["is_weekday"] | ((df["hour"] < 12) & ~df["is_weekday"])
    df["breathing"] = 0
    df.loc[flat_occupation, "breathing"] = 0  # 80.0

    weekday_shower = df["is_weekday"] & (df["hour"] == 7) & (df["minute"].isin([0, 15]))
    weekend_shower = ~df["is_weekday"] & (df["hour"] == 9) & (df["minute"].isin([0, 15]))
    df["shower"] = pd.NA
    df.loc[weekday_shower | weekend_shower, "shower"] = 0  # 200.0

    weekday_cooking = df["is_weekday"] & (df["hour"] >= 18) & (df["hour"] < 19)
    df["cooking"] = pd.NA
    df.loc[weekday_cooking, "cooking"] = 0  # 15.0

    return [
        _series_to_source(df["breathing"], "Breathing (1 person)"),
        _series_to_source(df["shower"], "Shower"),
        _series_to_source(df["cooking"], "Cooking (Dinner)"),
    ]


def main() -> None:
    """Run an example humidity simulation."""
    # Use today as the simulation date so weather and prices align
    sim_date = datetime.now().strftime("%Y-%m-%d")

    # Fetch live weather from Open-Meteo
    weather_client = OpenMeteoClient()
    weather_forecast = weather_client.get_humidity_forecast(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        hourly=["relative_humidity_2m", "temperature_2m"],
        daily=None,
        past_days=0,
        forecast_days=2,
        timezone="UTC",
    )
    hourly = weather_forecast.hourly
    if hourly is None or hourly.relative_humidity_2m is None or hourly.temperature_2m is None:
        msg = "Open-Meteo response missing required hourly data"
        raise ValueError(msg)

    external_ambient_conditions = AmbientConditions(
        name="OpenMeteo",
        timestamps=[t.isoformat() for t in hourly.time],
        timestamp_format="ISO8601",
        timezone="UTC",
        relative_humidity=hourly.relative_humidity_2m,
        ambient_temperature=hourly.temperature_2m,
        ambient_temperature_unit="Celcius",
    )

    # Create a simulator for a room
    # 25 m² floor area, 2.5m ceiling height, 20°C internal temperature
    simulator = InternalHumiditySimulator(
        surface_area=25,
        surface_area_unit="m2",
        ceiling_height=2.5,
        ceiling_height_unit="m",
        internal_temperature=20,
        internal_temperature_unit="c",
        air_changes_per_hour=0.3,
    )

    humidity_sources = scenario_one_bed_flat(
        start_date=pd.Timestamp(sim_date),
        days=2,
    )

    # Dehumidifier: turns on at the weekday shower (07:15), runs until mid-morning
    # Typical domestic unit: 250W, 400 g/h extraction rate
    dehumidifier = Dehumidifier(
        name="dehumidifier",
        wattage=250.0,
        extraction_rate=400.0,
        extraction_rate_unit="g/h",
        timestamps=[
            f"{sim_date} 07:00",
            f"{sim_date} 07:15",
            f"{sim_date} 08:00",
            f"{sim_date} 09:00",
            f"{sim_date} 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[0, 1, 1, 0, 0],  # on during shower and recovery period
    )

    # Fetch Agile electricity price forecast from the API (region H = Southern England)
    agile_client = AgilePredictClient()
    agile_forecasts = agile_client.get_forecast(region="H", days=1)
    energy_forecast = EnergyForecastTimeSeries.model_validate(agile_forecasts[0].to_timeseries().model_dump())

    dehumidifier = None

    # Run simulation starting at 50% relative humidity
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_name = f"humidity_simulation_{timestamp_str}"

    start_time = datetime.now()

    simulator.simulate(
        starting_relative_humidity=50,
        humidity_sources=humidity_sources,
        external_ambient_conditions=external_ambient_conditions,
        dehumidifier=dehumidifier,
        energy_forecast=energy_forecast,
        plot_results=True,
        plot_name=plot_name,
    )

    print(f"Simulation run time: {(datetime.now() - start_time)}")


if __name__ == "__main__":
    main()
