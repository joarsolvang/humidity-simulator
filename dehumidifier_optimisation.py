from datetime import datetime

from matplotlib import pyplot as plt
from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import HumiditySource
import pandas as pd
from pathlib import Path
import json
from humidity_simulator.models.energy_forecast import EnergyForecastTimeSeries
import pulp as pl


TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
TIMEZONE = "UTC"
DEFAULT_SIMULATION_DAYS = 14
DEFAULT_TIME_RESOLUTION = "15min"
PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs"


def _build_scenario_df(start_date: pd.Timestamp, days: int, time_resolution: str) -> pd.DataFrame:
    """Build a DataFrame with a datetime index and calendar metadata columns.

    Args:
        start_date: First day of the simulation.
        days: Number of days to simulate.
        time_resolution: Frequency string for the datetime index (e.g. "15min", "30min").

    Returns:
        DataFrame indexed by datetime with columns: is_weekday, hour, minute.
    """
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

    # Breathing: constant 80 g/h at all times
    flat_occupation = df["is_weekday"] | ((df["hour"] < 12) & ~df["is_weekday"])
    df["breathing"] = 0
    df.loc[flat_occupation, "breathing"] = 80.0

    # Shower: 15-min burst (weekday 07:00-07:15, weekend 09:00-09:15)
    weekday_shower = df["is_weekday"] & (df["hour"] == 7) & (df["minute"].isin([0, 15]))
    weekend_shower = ~df["is_weekday"] & (df["hour"] == 9) & (df["minute"].isin([0, 15]))
    df["shower"] = pd.NA
    df.loc[weekday_shower | weekend_shower, "shower"] = 200.0

    # Cooking: weekday evenings 18:00-19:00
    weekday_cooking = df["is_weekday"] & (df["hour"] >= 18) & (df["hour"] < 19)
    df["cooking"] = pd.NA
    df.loc[weekday_cooking, "cooking"] = 15.0

    return [
        _series_to_source(df["breathing"], "Breathing (1 person)"),
        _series_to_source(df["shower"], "Shower"),
        _series_to_source(df["cooking"], "Cooking (Dinner)"),
    ]


SCENARIO_FACTORIES = {
    "1 Bed Flat": scenario_one_bed_flat,
}


def load_price_forecast() -> EnergyForecastTimeSeries:
    price_forecast = Path(r"C:\Users\joar_\Documents\Github\humidity-simulator\notebooks\data\agile_14_days.json")
    with Path.open(price_forecast) as file:
        data = json.load(file)
        forecast = EnergyForecastTimeSeries.model_validate(data)
    return forecast


if __name__ == "__main__":
    start_date = pd.Timestamp(year=2026, month=2, day=24)
    humidity_scenario = scenario_one_bed_flat(start_date=start_date)

    simulator = InternalHumiditySimulator(
        surface_area=25,
        surface_area_unit="m2",
        ceiling_height=2.5,
        ceiling_height_unit="m",
        internal_temperature=20,
        internal_temperature_unit="c",
    )

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_name = f"humidity_simulation_{timestamp_str}"

    result = simulator.simulate(
        starting_relative_humidity=50,
        humidity_sources=humidity_scenario,
    )

    emissions_df = simulator._build_emissions_dataframe(humidity_scenario)
    forecast = load_price_forecast()
    timestamps = pd.to_datetime(forecast.timestamps)
    elec_price = pd.Series(forecast.values, index=timestamps, name="Electricity Price")
    timestamps = pd.to_datetime(result.timestamps)
    relative_humidity_forecast = pd.Series(
        result.relative_humidity, index=timestamps, name="Relative Humidity Forecast"
    )
    absolute_humidity_forecast = pd.Series(
        result.absolute_humidity, index=timestamps, name="Absolute Humidity Forecast"
    )

    data_df = elec_price.to_frame()
    data_df = data_df.join(relative_humidity_forecast.to_frame())
    data_df = data_df.join(absolute_humidity_forecast.to_frame())
    data_df = data_df.dropna()

    optimisation_df = data_df.loc[data_df.index[0] : data_df.index[0] + pd.Timedelta(days=1)]
    opt_emissions_df = emissions_df.loc[emissions_df.index[0] : emissions_df.index[0] + pd.Timedelta(days=2)]

    min_relative_humidity = 40
    max_relative_humidity = 60
    dehumidifier_wattage = 350
    time_stamps = list(optimisation_df.index)
    cost_of_energy = optimisation_df["Electricity Price"].to_list()
    time_delta = 0.25
    forecast_absolute_humidity = optimisation_df["Absolute Humidity Forecast"].to_list()
    temperature_celsius = 20
    extraction_rate = -400  # g/h

    upper = simulator._absolute_humidity_from_relative(60, temperature_celsius=temperature_celsius)
    lower = simulator._absolute_humidity_from_relative(40, temperature_celsius=temperature_celsius)

    prob = pl.LpProblem("Dehumidifier_Controller", pl.LpMinimize)
    controller_on = pl.LpVariable.dicts("controller_on", range(len(time_stamps)), cat=pl.LpBinary)
    absolute_humidity = pl.LpVariable.dicts("absolute_humidity", range(len(time_stamps)), lowBound=lower, upBound=upper)
    humidity_extracted = pl.LpVariable.dicts("humidity_extracted", range(len(time_stamps)))
    ventilation = pl.LpVariable.dicts("humidity_extracted", range(len(time_stamps)))

    t_kelvin = temperature_celsius + 273.15
    e_s = simulator._saturation_vapor_pressure(temperature_celsius)
    rh_per_ah = (t_kelvin / 2.16679 / e_s) * 100  # linear scalar

    prob += pl.lpSum((cost_of_energy[i] * controller_on[i] * time_delta) for i in range(len(time_stamps)))

    for i in range(len(time_stamps) - 1):
        prob += (
            humidity_extracted[i + 1] == humidity_extracted[i] + controller_on[i] * extraction_rate * time_delta
        )  # g
    prob += humidity_extracted[0] == 0

    for i in range(len(time_stamps) - 1):
        prob += ventilation[i] == -(
            (absolute_humidity[i] * simulator._volume_m3) - (External_RH[i] * simulator._volume_m3 * ACH)
        )
    prob += humidity_extracted[0] == 0

    for i in range(len(time_stamps) - 1):
        prob += (
            absolute_humidity[i]
            == ((forecast_absolute_humidity[i] * simulator._volume_m3) + humidity_extracted[i] + ventilation[i])
            / simulator._volume_m3
        )
    prob += absolute_humidity[0] == forecast_absolute_humidity[0]

    prob.solve(pl.PULP_CBC_CMD(msg=True, timeLimit=15))

    controller_on_solution = [controller_on[i].varValue for i in range(len(time_stamps) - 1)]
    humidity_extracted_solution = [humidity_extracted[i].varValue for i in range(len(time_stamps) - 1)]
    absolute_humidity_solution = [absolute_humidity[i].varValue for i in range(len(time_stamps) - 1)]
    relative_humidity_solution = [
        simulator._relative_humidity_from_absolute(absolute_humidity, temperature_celsius)
        for absolute_humidity in absolute_humidity_solution
    ]

    fig, ax = plt.subplots(nrows=4, figsize=(12, 12))
    ax[0].step(time_stamps, optimisation_df["Electricity Price"], where="post")

    bar_width = time_stamps[1] - time_stamps[0]
    dispatch_labeled = False
    charge_labeled = False

    for t, on in zip(time_stamps, controller_on_solution):
        if on:
            ax[0].axvspan(
                t, t + bar_width, alpha=0.3, color="green", label="Controller On" if not dispatch_labeled else None
            )
            dispatch_labeled = True

    ax[0].set_xlabel("Time")
    ax[0].set_ylabel("Cost of Electricity (£)")
    ax[0].grid()
    ax[0].legend()

    ax[1].plot(opt_emissions_df.index, opt_emissions_df["Breathing (1 person) (g/h)"], label="Breathing (1 person)")
    ax[1].plot(opt_emissions_df.index, opt_emissions_df["Shower (g/h)"], label="Shower")
    ax[1].plot(opt_emissions_df.index, opt_emissions_df["Cooking (Dinner) (g/h)"], label="Cooking")
    ax[1].set_xlabel("Time")
    ax[1].set_ylabel("Humidity Emissions [g/h]")
    ax[1].grid()
    ax[1].legend()

    ax[2].step(
        time_stamps[:-1],
        absolute_humidity_solution,
    )
    ax[2].set_xlabel("Time")
    ax[2].set_ylabel("Absolute Humidity [g/m3]")
    ax[2].grid()

    ax[3].step(
        time_stamps[:-1],
        relative_humidity_solution,
    )
    ax[3].set_xlabel("Time")
    ax[3].set_ylabel("Relative Humidity")
    ax[3].grid()

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_name = f"humidity_simulation_{timestamp_str}"
    output_file = DEFAULT_OUTPUT_PATH / f"{plot_name}.png"
    fig.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
