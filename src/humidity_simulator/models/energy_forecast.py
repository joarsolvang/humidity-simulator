from typing import Literal

from pydantic import BaseModel, model_validator


class EnergyForecastTimeSeries(BaseModel):
    """Agile energy price forecast timeseries.

    Mirrors the EnergyForecastTimeSeries produced by the agile_predict_api,
    allowing JSON files saved by that package to be parsed directly.

    Attributes:
        timestamps: List of ISO 8601 timestamp strings for each half-hourly price point.
        timestamp_format: Format description for the timestamps (e.g. "ISO 8601").
        timezone: Timezone of the timestamps (e.g. "UTC").
        values: Electricity price at each timestamp.
        values_unit: Unit for the price values.
    """

    timestamps: list[str]
    timestamp_format: str
    timezone: str
    values: list[float]
    values_unit: Literal["p/kWh"]

    @model_validator(mode="after")
    def validate_timeseries_length(self) -> "EnergyForecastTimeSeries":
        """Ensure timestamps and values have the same length."""
        if len(self.timestamps) != len(self.values):
            msg = (
                f"Timestamps and values must have the same length. "
                f"Got {len(self.timestamps)} timestamps and {len(self.values)} values."
            )
            raise ValueError(msg)
        return self
