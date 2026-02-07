"""FastAPI application for the humidity simulation API.

Run with: uvicorn humidity_simulator.api:app --reload
"""

import logging

import pandas as pd
from fastapi import FastAPI

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import SimulationRequest, SimulationResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Humidity Simulator API",
    description="Simulate internal humidity levels based on humidity sources",
    version="0.1.0",
)


@app.post("/simulate", response_model=SimulationResult)
def simulate(request: SimulationRequest) -> SimulationResult:
    """Run a humidity simulation.

    Takes room configuration and humidity sources, returns humidity over time.
    """
    logger.info(f"Received simulation request with {len(request.sources)} sources")

    # Step 1: Create the simulator with room configuration
    simulator = InternalHumiditySimulator(
        surface_area=request.surface_area,
        surface_area_unit=request.surface_area_unit,
        ceiling_height=request.ceiling_height,
        ceiling_height_unit=request.ceiling_height_unit,
        internal_temperature=request.internal_temperature,
        internal_temperature_unit=request.internal_temperature_unit,
    )

    # Step 2: Convert time resolution from minutes to pandas Timedelta
    time_resolution = pd.Timedelta(minutes=request.time_resolution_minutes)

    # Step 3: Run the simulation
    # request.sources is already a list of HumiditySource objects (Pydantic parsed them)
    result = simulator.simulate(
        starting_relative_humidity=request.starting_relative_humidity,
        humidity_sources=request.sources,
        time_resolution=time_resolution,
    )

    logger.info(f"Simulation complete, returning {len(result.timestamps)} data points")
    return result


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
