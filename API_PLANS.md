# API Implementation Plans

This document outlines the plan to expose the humidity simulation engine as an API.

## Overview

Turn the `InternalHumiditySimulator` into a REST API that accepts humidity source data and returns simulation results as JSON.

## Framework

**FastAPI** - modern Python web framework with automatic OpenAPI documentation.

## Code Changes Required

1. Add FastAPI and uvicorn dependencies to `pyproject.toml`
2. Create `api.py` in project root with endpoints
3. Define Pydantic request/response models (based on existing dataclasses)
4. Create a Dockerfile for containerization

### Example Endpoint Structure

```python
POST /simulate
{
    "starting_humidity": 50,
    "time_resolution_minutes": 30,
    "sources": [
        {
            "name": "shower",
            "timestamps": ["2024-01-01 07:00", "2024-01-01 07:30"],
            "timestamp_format": "%Y-%m-%d %H:%M",
            "timezone": "UTC",
            "values": [0.0, 400.0],
            "values_unit": "g/h"
        }
    ]
}
```

## Hosting Decision

**Azure Container Apps** (recommended)

- Scale to zero (no cost when idle)
- Simple container deployment
- Auto-scaling for traffic spikes
- No infrastructure management

### Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Azure Functions | Cheapest for infrequent use | Cold start delays |
| Azure App Service | Simple, always on | Minimum ~$13/month |
| Azure Kubernetes Service | Full control, scalable | Complex, expensive |

## Deployment Pipeline

```
GitHub repo → GitHub Actions → Build Docker image → Azure Container Registry → Azure Container Apps
```

## Prerequisites

- Azure account (free tier has $200 credit)
- Azure Container Registry (to store Docker images)
- GitHub Actions workflow for CI/CD

## TODO

- [ ] Add FastAPI and uvicorn to dependencies
- [ ] Create Pydantic models for request/response
- [ ] Create API endpoints in `api.py`
- [ ] Create Dockerfile
- [ ] Create GitHub Actions workflow for Azure deployment
- [ ] Set up Azure Container Registry
- [ ] Set up Azure Container Apps
