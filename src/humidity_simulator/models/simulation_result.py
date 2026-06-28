from pydantic import BaseModel


class SimulationResult(BaseModel):
    """Results from a humidity simulation.

    Attributes:
        timestamps: List of timestamp strings for each simulation step.
        relative_humidity: List of relative humidity values (%) at each timestamp.
        absolute_humidity: List of absolute humidity values (g/m³) at each timestamp.
        dehumidifier_running_cost_pence: Cost of electricity consumed by the dehumidifier
            at each timestamp (pence). None if no energy forecast was provided.
    """

    timestamps: list[str]
    relative_humidity: list[float]
    absolute_humidity: list[float]
    dehumidifier_running_cost_pence: list[float] | None = None
