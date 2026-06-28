"""FastAPI application for the humidity simulation API.

Run with: uvicorn dehumidifier_controller.main:app --reload
"""

import logging

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Humidity Simulator API",
    description="Simulate internal humidity levels based on humidity sources",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
