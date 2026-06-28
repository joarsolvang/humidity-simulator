import numpy as np
from pymoo.core.problem import ElementwiseProblem

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import Dehumidifier, EnergyForecastTimeSeries, HumiditySource
from humidity_simulator.models.humidity_source import AmbientConditions


class DehumidifierOptimisationProblem(ElementwiseProblem):
    """Binary optimisation problem: find the on/off schedule that minimises mean relative humidity."""

    HUMIDITY_PENALTY_PENCE = 5.0
    RH_THRESHOLD = 60.0

    def __init__(
        self,
        simulator: InternalHumiditySimulator,
        humidity_sources: list[HumiditySource],
        dehumidifier: Dehumidifier,
        external_ambient_conditions: AmbientConditions,
        schedule_timestamps: list[str],
        energy_forecast: EnergyForecastTimeSeries,
        starting_relative_humidity: float,
    ) -> None:
        self.simulator = simulator
        self.humidity_sources = humidity_sources
        self.dehumidifier = dehumidifier
        self.external_ambient_conditions = external_ambient_conditions
        self.schedule_timestamps = schedule_timestamps
        self.energy_forecast = energy_forecast
        self.starting_relative_humidity = starting_relative_humidity

        n_timesteps = len(schedule_timestamps)
        super().__init__(n_var=n_timesteps, n_obj=1, xl=0, xu=1)

    def _evaluate(self, x: np.ndarray, out: dict) -> None:  # type: ignore[override]
        binary_schedule = [round(float(v)) for v in x]

        self.dehumidifier.values = binary_schedule

        result = self.simulator.simulate(
            starting_relative_humidity=self.starting_relative_humidity,
            humidity_sources=self.humidity_sources,
            external_ambient_conditions=self.external_ambient_conditions,
            dehumidifier=self.dehumidifier,
            energy_forecast=self.energy_forecast,
        )

        running_cost = sum(result.dehumidifier_running_cost_pence or [])
        overhumidity_penalty = self.HUMIDITY_PENALTY_PENCE * sum(
            1 for rh in result.relative_humidity if rh > self.RH_THRESHOLD
        )
        out["F"] = [running_cost + overhumidity_penalty]
