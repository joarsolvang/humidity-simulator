from typing import Literal
import pandas as pd
from pydantic import BaseModel, model_validator


class HumiditySource(BaseModel):
    """A source of humidity emissions with associated timeseries data.

    Attributes:
        name: Identifier for the humidity source (e.g., "shower", "cooking", "breathing").
        max_emissions_rate_unit: Unit for the maximum emissions rate.
        timestamps: List of timestamp strings representing when emissions occur.
        timestamp_format: Format string describing the timestamp format (e.g., "%Y-%m-%d %H:%M:%S").
        timezone: Timezone for the timestamps (e.g., "UTC", "Europe/London", "America/New_York").
        values: List of emission values corresponding to each timestamp.
        values_unit: Unit for the emission values.
    """

    name: str
    max_emissions_rate_unit: Literal["g/h", "kg/h", "lb/h"]
    timestamps: list[str]
    timestamp_format: str
    timezone: str
    values: list[float]
    values_unit: Literal["g/h", "kg/h", "lb/h"]

    @model_validator(mode="after")
    def validate_timeseries_length(self) -> "HumiditySource":
        """Ensure timestamps and values have the same length."""
        if len(self.timestamps) != len(self.values):
            msg = (
                f"Timestamps and values must have the same length. "
                f"Got {len(self.timestamps)} timestamps and {len(self.values)} values."
            )
            raise ValueError(msg)
        return self


class AmbientConditions(BaseModel):
    """A source of humidity emissions with associated timeseries data.

    Attributes:
        name: Identifier for data.
        timestamps: List of timestamp strings representing when emissions occur.
        timestamp_format: Format string describing the timestamp format (e.g., "%Y-%m-%d %H:%M:%S").
        timezone: Timezone for the timestamps (e.g., "UTC", "Europe/London", "America/New_York").
        values: List of emission values corresponding to each timestamp.
        values_unit: Unit for the emission values.
    """

    name: str
    timestamps: list[str]
    timestamp_format: str
    timezone: str
    relative_humidity: list[float]
    ambient_temperature: list[float]
    ambient_temperature_unit: Literal["Celcius"]

    @model_validator(mode="after")
    def validate_timeseries_length(self) -> "HumiditySource":
        """Ensure timestamps and values have the same length."""
        if len(self.timestamps) != len(self.relative_humidity) or len(self.timestamps) != len(self.ambient_temperature):
            msg = (
                f"Timestamps and values must have the same length. "
                f"Timestamps = {len(self.timestamps)}"
                f"Relative Humidity = {len(self.relative_humidity)}"
                f"Ambient Temperature = {len(self.ambient_temperature)}"
            )
            raise ValueError(msg)
        return self

    def to_dateframe(self) -> pd.DataFrame:
            return pd.DataFrame(
        index=[pd.to_datetime(
            timestamp,
            format=self.timestamp_format,
            ).tz_localize(self.timezone)
            for timestamp in self.timestamps],
        data={
            "relative_humidity_2m": self.relative_humidity,
            "ambient_temperature": self.ambient_temperature
        }
    )
