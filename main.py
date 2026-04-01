"""Example usage of the humidity simulator."""

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import Dehumidifier, HumiditySource
from humidity_simulator.models.humidity_source import AmbientConditions

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "example_data"


def main() -> None:
    """Run an example humidity simulation."""
    ambient_conditions_file_name = "forecast_hourly.csv"
    ambient_conditions = pd.read_csv(DATA_DIR / ambient_conditions_file_name)

    external_ambient_conditions = AmbientConditions(
        name="OpenMeteo",
        timestamps=ambient_conditions["time"],
        timestamp_format="ISO8601",
        timezone="UTC",
        relative_humidity=ambient_conditions["relative_humidity_2m"],
        ambient_temperature=ambient_conditions["temperature_2m"],
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
        air_changes_per_hour=0.1,
    )

    shower = HumiditySource(
        name="shower",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2026-03-02 07:00",
            "2026-03-02 07:15",
            "2026-03-02 07:30",
            "2026-03-02 08:00",
            "2026-03-02 09:00",
            "2026-03-02 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[0.0, 400.0, 200.0, 0.0, 0.0, 0.0],  # g/h emission rate
        values_unit="g/h",
    )

    breathing = HumiditySource(
        name="breathing",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2026-03-02 07:00",
            "2026-03-02 08:00",
            "2026-03-02 09:00",
            "2026-03-02 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[40.0, 40.0, 40.0, 40.0],  # ~40 g/h per person
        values_unit="g/h",
    )

    # Cooking: emissions during breakfast
    cooking = HumiditySource(
        name="cooking",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2026-03-02 07:00",
            "2026-03-02 07:30",
            "2026-03-02 08:00",
            "2026-03-02 08:30",
            "2026-03-02 09:00",
            "2026-03-02 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[0.0, 150.0, 100.0, 0.0, 0.0, 0.0],
        values_unit="g/h",
    )

    # Dehumidifier: turns on as the shower starts, runs until mid-morning
    # Typical domestic unit: 250W, 700 g/h extraction rate
    dehumidifier = Dehumidifier(
        name="dehumidifier",
        wattage=250.0,
        extraction_rate=400.0,
        extraction_rate_unit="g/h",
        timestamps=[
            "2026-03-02 07:00",
            "2026-03-02 07:15",
            "2026-03-02 08:00",
            "2026-03-02 09:00",
            "2026-03-02 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[0, 1, 1, 0, 0],  # on during shower and recovery period
    )

    # Run simulation starting at 50% relative humidity
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_name = f"humidity_simulation_{timestamp_str}"

    start_time = datetime.now()

    simulator.simulate(
        starting_relative_humidity=50,
        humidity_sources=[shower, breathing, cooking],
        external_ambient_conditions=external_ambient_conditions,
        dehumidifier=dehumidifier,
        plot_results=True,
        plot_name=plot_name,
    )

    print(f"{datetime.now() - start_time}")


if __name__ == "__main__":
    main()
