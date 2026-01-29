from dataclasses import dataclass
from typing import Literal


@dataclass
class HumiditySource:
    """A source of humidity emissions with associated timeseries data.

    Attributes:
        name: Identifier for the humidity source (e.g., "shower", "cooking", "breathing").
        max_emissions_rate: Maximum emission rate the source can produce.
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

    def __post_init__(self) -> None:
        """Validate the humidity source data after initialization."""
        self._validate_timeseries_length()

    def _validate_timeseries_length(self) -> None:
        """Ensure timestamps and values have the same length."""
        if len(self.timestamps) != len(self.values):
            msg = (
                f"Timestamps and values must have the same length. "
                f"Got {len(self.timestamps)} timestamps and {len(self.values)} values."
            )
            raise ValueError(msg)
