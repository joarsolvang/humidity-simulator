from pydantic import BaseModel


class SimulationResult(BaseModel):
    """Results from a humidity simulation.

    Attributes:
        timestamps: List of timestamp strings for each simulation step.
        relative_humidity: List of relative humidity values (%) at each timestamp.
        absolute_humidity: List of absolute humidity values (g/m³) at each timestamp.
    """

    timestamps: list[str]
    relative_humidity: list[float]
    absolute_humidity: list[float]
