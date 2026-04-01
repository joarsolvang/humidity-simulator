import logging
from pathlib import Path
from typing import ClassVar, Literal
from zoneinfo import ZoneInfoNotFoundError

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from humidity_simulator.models import Dehumidifier, HumiditySource, SimulationResult
from humidity_simulator.models.humidity_source import AmbientConditions

logger = logging.getLogger(__name__)

TIMEZONE_HELP_URL = "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"

# Project root is 4 levels up from this file (engine -> humidity_simulator -> src -> root)
PROJECT_ROOT = Path(__file__).parents[3]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs"
DEFAULT_TIME_RESOLUTION = pd.Timedelta(minutes=30)

UnitSystem = Literal["metric", "imperial"]


class UnitConsistencyError(Exception):
    """Raised when input units are inconsistent."""


class InternalHumiditySimulator:
    """Simulator of internal humidity."""

    METRIC_UNITS: ClassVar[set[str]] = {"m2", "m", "c", "k"}
    IMPERIAL_UNITS: ClassVar[set[str]] = {"ft2", "ft", "f"}

    # Conversion factors to metric base units
    AREA_TO_M2: ClassVar[dict[str, float]] = {"m2": 1.0, "ft2": 0.092903}
    HEIGHT_TO_M: ClassVar[dict[str, float]] = {"m": 1.0, "ft": 0.3048}
    EMISSION_TO_G_PER_H: ClassVar[dict[str, float]] = {"g/h": 1.0, "kg/h": 1000.0, "lb/h": 453.592}

    def __init__(
        self,
        surface_area: float | int,
        surface_area_unit: Literal["m2", "ft2"],
        ceiling_height: float | int,
        ceiling_height_unit: Literal["m", "ft"],
        internal_temperature: float | int,
        internal_temperature_unit: Literal["c", "k", "f"],
        air_changes_per_hour: float,
    ) -> None:
        self._validate_unit_consistency(surface_area_unit, ceiling_height_unit, internal_temperature_unit)

        self.surface_area = surface_area
        self.surface_area_unit = surface_area_unit
        self.ceiling_height = ceiling_height
        self.ceiling_height_unit = ceiling_height_unit
        self.internal_temperature = internal_temperature
        self.internal_temperature_unit = internal_temperature_unit
        self.environment_volume = self.surface_area * self.ceiling_height
        self.air_changes_per_hour = air_changes_per_hour

        # Store metric values for calculations
        self._volume_m3 = self._calculate_volume_m3()
        self._temperature_celsius = self._to_celsius(internal_temperature, internal_temperature_unit)

    @property
    def volume_m3(self) -> float:
        """Room volume in cubic meters."""
        return self._volume_m3

    @property
    def temperature_celsius(self) -> float:
        """Internal temperature in degrees Celsius."""
        return self._temperature_celsius

    def _calculate_volume_m3(self) -> float:
        """Calculate room volume in cubic meters."""
        area_m2 = self.surface_area * self.AREA_TO_M2[self.surface_area_unit]
        height_m = self.ceiling_height * self.HEIGHT_TO_M[self.ceiling_height_unit]
        return area_m2 * height_m

    def _to_celsius(self, temperature: float | int, unit: str) -> float:
        """Convert temperature to Celsius."""
        if unit == "c":
            return float(temperature)
        if unit == "k":
            return float(temperature) - 273.15
        if unit == "f":
            return (float(temperature) - 32) * 5 / 9
        msg = f"Unknown temperature unit: {unit}"
        raise ValueError(msg)

    def _saturation_vapor_pressure(self, temperature_celsius: float | np.ndarray) -> float | np.ndarray:
        """Calculate saturation vapor pressure using Magnus-Tetens formula.

        Args:
            temperature_celsius: Temperature in degrees Celsius.

        Returns:
            Saturation vapor pressure in Pascals.
        """
        return 610.94 * np.exp((17.625 * temperature_celsius) / (temperature_celsius + 243.04))

    def _absolute_humidity_from_relative(
        self,
        relative_humidity: float | np.ndarray,
        temperature_celsius: float | np.ndarray,
    ) -> float | np.ndarray:
        """Convert relative humidity to absolute humidity.

        Args:
            relative_humidity: Relative humidity in percent (0-100).
            temperature_celsius: Temperature in degrees Celsius.

        Returns:
            Absolute humidity in g/m³.
        """
        e_s = self._saturation_vapor_pressure(temperature_celsius)
        e = (relative_humidity / 100) * e_s
        t_kelvin = temperature_celsius + 273.15
        # Absolute humidity formula: AH = (e * Mw) / (R * T)
        # Mw = 18.015 g/mol, R = 8.314 J/(mol·K)
        # Simplified: AH = 2.16679 * e / T_kelvin (g/m³)
        return 2.16679 * e / t_kelvin

    def _relative_humidity_from_absolute(self, absolute_humidity: float, temperature_celsius: float) -> float:
        """Convert absolute humidity to relative humidity.

        Args:
            absolute_humidity: Absolute humidity in g/m³.
            temperature_celsius: Temperature in degrees Celsius.

        Returns:
            Relative humidity in percent (0-100), capped at 100%.
        """
        t_kelvin = temperature_celsius + 273.15
        e = absolute_humidity * t_kelvin / 2.16679
        e_s = self._saturation_vapor_pressure(temperature_celsius)
        rh = (e / e_s) * 100
        return min(float(rh), 100.0)  # Cap at 100% (condensation occurs beyond this)

    def _build_emissions_dataframe(
        self,
        humidity_sources: list[HumiditySource],
        time_resolution: pd.Timedelta = DEFAULT_TIME_RESOLUTION,
        target_timezone: str = "UTC",
    ) -> pd.DataFrame:
        """Build a DataFrame of emissions from all sources with aligned timestamps.

        Converts all timeseries to a common timezone, resamples all data to the
        specified time resolution with forward fill, and joins into a single DataFrame.

        Args:
            humidity_sources: List of humidity sources with timeseries data.
            time_resolution: Time resolution for the output DataFrame. Defaults to 30 minutes.
            target_timezone: Timezone to standardize all timestamps to. Defaults to "UTC".

        Returns:
            DataFrame with DatetimeIndex and one column per humidity source (in g/h).
        """
        logger.info(f"Building emissions dataframe with time resolution: {time_resolution}")
        series_list: list[pd.Series] = []

        for source in humidity_sources:
            timestamps = pd.to_datetime(
                source.timestamps,
                format=source.timestamp_format,
            )
            if timestamps.tz is None:
                try:
                    timestamps = timestamps.tz_localize(source.timezone)
                except ZoneInfoNotFoundError as e:
                    msg = f"{e}. See {TIMEZONE_HELP_URL} for a list of valid TZ identifiers."
                    raise ZoneInfoNotFoundError(msg) from None
            else:
                logger.warning(
                    f"Source '{source.name}' has timezone info in timestamp format "
                    f"and also specifies timezone attribute '{source.timezone}'. "
                    "Using timezone from timestamp format."
                )

            try:
                timestamps = timestamps.tz_convert(target_timezone)
            except ZoneInfoNotFoundError as e:
                msg = f"{e}. See {TIMEZONE_HELP_URL} for a list of valid TZ identifiers."
                raise ZoneInfoNotFoundError(msg) from None

            # Convert values to g/h
            conversion_factor = self.EMISSION_TO_G_PER_H[source.values_unit]
            values = [v * conversion_factor for v in source.values]

            series = pd.Series(values, index=timestamps, name=f"{source.name} (g/h)")
            series_list.append(series)

        # Create a continuous date range
        all_timestamps = pd.concat([pd.Series(s.index) for s in series_list])
        min_time = all_timestamps.min()
        max_time = all_timestamps.max()
        continuous_index = pd.date_range(start=min_time, end=max_time, freq=time_resolution)

        # Resample each series within its own time range, then reindex to continuous range
        resampled_series = []
        for series in series_list:
            old_time_resolution = series.index[1] - series.index[0]
            fill_limit = max((old_time_resolution.seconds // time_resolution.seconds) - 1, 1)
            series_resampled = series.resample(time_resolution).ffill(limit=fill_limit)
            series_continuous = series_resampled.reindex(continuous_index)
            resampled_series.append(series_continuous)

        df = pd.concat(resampled_series, axis=1)
        return df.fillna(0.0)

    def _build_dehumidifier_series(
        self,
        dehumidifier: Dehumidifier,
        continuous_index: pd.DatetimeIndex,
        time_resolution: pd.Timedelta,
        target_timezone: str = "UTC",
    ) -> pd.Series:
        """Build a timeseries of dehumidifier extraction rates aligned to the simulation grid.

        Where the dehumidifier is on (value=1) the series holds the extraction rate in g/h;
        where it is off (value=0) or outside the schedule the series holds 0.0.

        Args:
            dehumidifier: Dehumidifier instance with schedule and metadata.
            continuous_index: The aligned DatetimeIndex used by the simulation.
            time_resolution: Simulation time resolution, used to set the ffill limit.
            target_timezone: Timezone to convert timestamps to. Defaults to "UTC".

        Returns:
            Series indexed by continuous_index with extraction rate in g/h at each step.
        """
        logger.info(f"Building dehumidifier series for '{dehumidifier.name}'")
        timestamps = pd.to_datetime(dehumidifier.timestamps, format=dehumidifier.timestamp_format)
        if timestamps.tz is None:
            timestamps = timestamps.tz_localize(dehumidifier.timezone)
        timestamps = timestamps.tz_convert(target_timezone)

        extraction_g_per_h = dehumidifier.extraction_rate * self.EMISSION_TO_G_PER_H[dehumidifier.extraction_rate_unit]
        values = [v * extraction_g_per_h for v in dehumidifier.values]

        series = pd.Series(values, index=timestamps, name=f"{dehumidifier.name} extraction (g/h)")

        if len(series) > 1:
            schedule_resolution = series.index[1] - series.index[0]
            fill_limit = max((schedule_resolution.seconds // time_resolution.seconds) - 1, 1)
        else:
            fill_limit = 1

        series_resampled = series.resample(time_resolution).ffill(limit=fill_limit)
        series_aligned = series_resampled.reindex(continuous_index, fill_value=0.0)
        return series_aligned

    def simulate(
        self,
        starting_relative_humidity: float | int,
        humidity_sources: list[HumiditySource],
        external_ambient_conditions: AmbientConditions,
        *,
        dehumidifier: Dehumidifier | None = None,
        time_resolution: pd.Timedelta = DEFAULT_TIME_RESOLUTION,
        plot_results: bool = False,
        plot_path: Path | str = DEFAULT_OUTPUT_PATH,
        plot_name: str | None = None,
    ) -> SimulationResult:
        """Run the humidity simulation.

        Args:
            starting_relative_humidity: Initial relative humidity in percent (0-100).
            humidity_sources: List of humidity sources with timeseries data.
            external_ambient_conditions: Class containing external ambient conditions.
            dehumidifier: Optional dehumidifier with binary on/off control schedule.
            time_resolution: Time resolution for the simulation. Defaults to 30 minutes.
            plot_results: If True, generate and save plots of the simulation results.
            plot_path: Directory path where plots will be saved. Defaults to "outputs".
            plot_name: Name for the plot file (without extension).

        Returns:
            SimulationResult containing timestamps and humidity values.
        """
        if not humidity_sources:
            return SimulationResult(timestamps=[], relative_humidity=[], absolute_humidity=[])

        emissions_df = self._build_emissions_dataframe(humidity_sources, time_resolution=time_resolution)

        if emissions_df.empty:
            return SimulationResult(timestamps=[], relative_humidity=[], absolute_humidity=[])

        # Calculate total emissions per timestamp
        total_emissions = emissions_df.sum(axis=1)

        # Assert all time deltas are equal (as expected from continuous date range)
        if len(emissions_df) > 1:
            time_deltas = emissions_df.index.to_series().diff().dropna()
            if not (time_deltas == time_resolution).all():
                msg = f"Expected uniform time resolution of {time_resolution}, but found varying deltas"
                raise ValueError(msg)

        # Convert time resolution to hours
        time_delta_hours = time_resolution.total_seconds() / 3600

        # Calculate water added at each step (g/m³)
        water_added_per_step = total_emissions * time_delta_hours
        water_added_per_step = water_added_per_step.to_frame(name="water added [g]")

        # Calculate cumulative absolute humidity
        starting_abs_humidity = self._absolute_humidity_from_relative(
            float(starting_relative_humidity), self._temperature_celsius
        )

        external_ambient_conditions_df = external_ambient_conditions.to_dateframe()
        external_ambient_conditions_df["External Absolute Humidity g/m3"] = self._absolute_humidity_from_relative(
            external_ambient_conditions_df["relative_humidity_2m"].values,
            external_ambient_conditions_df["ambient_temperature"].values,
        )
        external_ambient_conditions_df = external_ambient_conditions_df.resample(time_resolution).ffill()

        built_environment_df = external_ambient_conditions_df.join(water_added_per_step["water added [g]"])
        built_environment_df["water added [g]"] = built_environment_df["water added [g]"].fillna(0)

        if dehumidifier is not None:
            logger.info(f"Applying dehumidifier '{dehumidifier.name}' to simulation")
            dehumidifier_series = self._build_dehumidifier_series(
                dehumidifier, built_environment_df.index, time_resolution
            )
            built_environment_df["dehumidifier extracted [g]"] = (
                dehumidifier_series * time_delta_hours
            )
        else:
            built_environment_df["dehumidifier extracted [g]"] = 0.0

        simulated_absolute_humidity = [starting_abs_humidity]
        for i in range(len(built_environment_df) - 1):
            internal_humidity = simulated_absolute_humidity[i] * self._volume_m3 * (1 - self.air_changes_per_hour)
            external_humidity = (
                built_environment_df["External Absolute Humidity g/m3"].iloc[i]
                * self._volume_m3
                * self.air_changes_per_hour
            )
            added_humidity = built_environment_df["water added [g]"].iloc[i]

            next_absolute_humidity = (internal_humidity + external_humidity + added_humidity) / self._volume_m3
            next_relative_humidity = self._relative_humidity_from_absolute(next_absolute_humidity, self.temperature_celsius)

            extracted_humidity = built_environment_df["dehumidifier extracted [g]"].iloc[i]
            extracted_humidity*= self.apply_efficiency_reduction(next_relative_humidity)

            simulated_absolute_humidity.append(
                (next_absolute_humidity * self._volume_m3 - extracted_humidity) / self._volume_m3
            )

        built_environment_df["simulated_absolute_humidity"] = simulated_absolute_humidity

        # Calculate relative humidity (vectorized)
        t_kelvin = self._temperature_celsius + 273.15
        e = built_environment_df["simulated_absolute_humidity"] * t_kelvin / 2.16679
        e_s = self._saturation_vapor_pressure(self._temperature_celsius)
        built_environment_df["simulated_relative_humidity"] = ((e / e_s) * 100).clip(upper=100.0)

        # Build result
        result = SimulationResult(
            timestamps=[ts.isoformat() for ts in built_environment_df.index],
            relative_humidity=built_environment_df["simulated_relative_humidity"].round(4).tolist(),
            absolute_humidity=built_environment_df["simulated_absolute_humidity"].round(4).tolist(),
        )

        if plot_results:
            if plot_name is None:
                msg = "plot_name is required when plot_results=True"
                raise ValueError(msg)
            self._plot_results(built_environment_df, Path(plot_path), plot_name)

        return result


    def apply_efficiency_reduction(self, relative_humidity: int) -> float:
        return min(1, relative_humidity**2/70**2)

    def _plot_results(
        self,
        built_environment_df: pd.DataFrame,
        plot_path: Path,
        plot_name: str,
    ) -> None:
        """Generate and save plots of the simulation results.

        Args:
            built_environment_df: The full simulation DataFrame including ambient conditions,
                humidity sources, dehumidifier schedule, and simulated results.
            plot_path: Directory path where plots will be saved.
            plot_name: Base name for the plot file (without extension).
        """
        plot_path.mkdir(parents=True, exist_ok=True)

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12), sharex=True)

        # --- Subplot 1: Ambient conditions ---
        ax1.set_title("Simulation Results")
        ax1_rh = ax1
        ax1_temp = ax1.twinx()

        ax1_rh.plot(
            built_environment_df.index,
            built_environment_df["relative_humidity_2m"],
            color="steelblue",
            linewidth=1.5,
            label="External RH (%)",
        )
        ax1_temp.plot(
            built_environment_df.index,
            built_environment_df["ambient_temperature"],
            color="tomato",
            linewidth=1.5,
            linestyle="--",
            label="External Temp (°C)",
        )
        ax1_rh.set_ylabel("Relative Humidity (%)")
        ax1_temp.set_ylabel("Temperature (°C)")
        ax1_rh.set_ylim(0, 105)

        lines1 = ax1_rh.get_lines() + ax1_temp.get_lines()
        ax1_rh.legend(lines1, [l.get_label() for l in lines1], loc="upper right")
        ax1_rh.grid(alpha=0.3)

        # --- Subplot 2: Humidity added and extracted ---
        ax2.plot(
            built_environment_df.index,
            built_environment_df["water added [g]"],
            color="royalblue",
            linewidth=1.5,
            drawstyle="steps-post",
            label="Added (g)",
        )
        ax2.plot(
            built_environment_df.index,
            built_environment_df["dehumidifier extracted [g]"],
            color="darkorange",
            linewidth=1.5,
            drawstyle="steps-post",
            label="Extracted (g)",
        )
        ax2.set_ylabel("Humidity per step (g)")
        ax2.legend(loc="upper right")
        ax2.grid(alpha=0.3)

        # --- Subplot 3: Simulated results (twin y-axis) ---
        ax3_rh = ax3
        ax3_abs = ax3.twinx()

        ax3_rh.plot(
            built_environment_df.index,
            built_environment_df["simulated_relative_humidity"],
            color="steelblue",
            linewidth=2,
            label="Relative Humidity (%)",
        )
        ax3_rh.axhline(y=60, color="orange", linestyle="--", alpha=0.5, label="Max recommended (60%)")
        ax3_rh.axhline(y=40, color="green", linestyle="--", alpha=0.5, label="Min recommended (40%)")
        ax3_rh.set_ylabel("Relative Humidity (%)")
        ax3_rh.set_ylim(0, 105)
        ax3_rh.set_xlabel("Time")

        ax3_abs.plot(
            built_environment_df.index,
            built_environment_df["simulated_absolute_humidity"],
            color="seagreen",
            linewidth=2,
            linestyle="--",
            label="Absolute Humidity (g/m³)",
        )
        ax3_abs.set_ylabel("Absolute Humidity (g/m³)")

        lines3 = ax3_rh.get_lines() + ax3_abs.get_lines()
        ax3_rh.legend(lines3, [l.get_label() for l in lines3], loc="upper right")
        ax3_rh.grid(alpha=0.3)

        plt.xticks(rotation=45)
        plt.tight_layout()

        output_file = plot_path / f"{plot_name}.png"
        fig.savefig(output_file, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"Plot saved to: {output_file}")

    def _get_unit_system(self, unit: str) -> UnitSystem:
        """Determine whether a unit belongs to metric or imperial system."""
        if unit in self.METRIC_UNITS:
            return "metric"
        if unit in self.IMPERIAL_UNITS:
            return "imperial"
        msg = f"Unknown unit: {unit}"
        raise ValueError(msg)

    def _validate_unit_consistency(
        self,
        surface_area_unit: str,
        ceiling_height_unit: str,
        temperature_unit: str,
    ) -> None:
        """Validate that all input units belong to the same unit system.

        Raises:
            UnitConsistencyError: If units are from mixed systems (metric and imperial).
        """
        units = {
            "surface_area_unit": surface_area_unit,
            "ceiling_height_unit": ceiling_height_unit,
            "temperature_unit": temperature_unit,
        }

        systems = {name: self._get_unit_system(unit) for name, unit in units.items()}
        unique_systems = set(systems.values())

        if len(unique_systems) > 1:
            details = ", ".join(f"{name}={system}" for name, system in systems.items())
            msg = f"Inconsistent unit systems: {details}. All units must be metric or imperial."
            raise UnitConsistencyError(msg)
