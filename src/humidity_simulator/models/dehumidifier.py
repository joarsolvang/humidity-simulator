from typing import Literal

from pydantic import BaseModel, model_validator


class Dehumidifier(BaseModel):
    """A dehumidifier appliance with a binary on/off control schedule.

    Attributes:
        name: Identifier for the dehumidifier.
        wattage: Power consumption of the appliance in Watts.
        extraction_rate: Rate at which the dehumidifier removes moisture from the air.
        extraction_rate_unit: Unit for the extraction rate.
        timestamps: List of timestamp strings for the control schedule.
        timestamp_format: Format string describing the timestamp format.
        timezone: Timezone for the timestamps (e.g., "UTC", "Europe/London").
        values: Binary control schedule (1 = on, 0 = off).
    """

    name: str
    wattage: float
    extraction_rate: float
    extraction_rate_unit: Literal["g/h", "kg/h", "lb/h"]
    timestamps: list[str]
    timestamp_format: str
    timezone: str
    values: list[int]

    @model_validator(mode="after")
    def validate_timeseries(self) -> "Dehumidifier":
        """Ensure timestamps and values have the same length and values are binary."""
        if len(self.timestamps) != len(self.values):
            msg = (
                f"Timestamps and values must have the same length. "
                f"Got {len(self.timestamps)} timestamps and {len(self.values)} values."
            )
            raise ValueError(msg)
        if not all(v in (0, 1) for v in self.values):
            msg = "Dehumidifier values must be binary (0 or 1)."
            raise ValueError(msg)
        return self
