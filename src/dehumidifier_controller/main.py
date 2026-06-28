"""Combined FastAPI application: simulation + optimisation.

Run with:
    uvicorn dehumidifier_controller.main:app --reload
"""

from dehumidifier_controller.api_router import optimisation_router, simulation_router
from humidity_simulator.api import app

app.include_router(simulation_router)
app.include_router(optimisation_router)

__all__ = ["app"]
