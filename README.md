# humidity-simulator

The simulation and optimisation API behind [Tørk](https://dehumidifier-advisor.streamlit.app/)
([dehumidifier-advisor](https://github.com/joarsolvang/dehumidifier-advisor)).

The calculation engine models the internal humidity of a property based on internal sources of humidity, external weather forecasts and settings such as size, temperature and ventilation. A optimiser also solves for the optimum dehumidifier schedule balancing the electricity price and indoor environment guidelines.

## API

A [FastAPI](https://fastapi.tiangolo.com/) service with the following endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check |
| `/simulate` | POST | Simulate internal humidity for a room, with no dehumidifier |
| `/optimisation` | POST | Find a dehumidifier schedule for a room and an electricity price forecast |

When running locally, interactive documentation with the full request and response schemas is at
`http://localhost:8000/docs`.

## Running locally with Docker

### 1. Install Docker

- **Windows**: [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- **macOS**: [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
- **Linux**: [Docker Engine](https://docs.docker.com/engine/install/) and the
  [Docker Compose plugin](https://docs.docker.com/compose/install/linux/)

Docker Desktop includes Docker Compose. Make sure Docker is running before continuing.

### 2. Start the API

```bash
docker compose up -d --build
```

The API is now available at `http://localhost:8000`, which is where the dehumidifier-advisor app looks for it by
default. 

To stop it:

```bash
docker compose down
```

## Deployment

The API is deployed to Azure Functions. Every push to `main` runs the CI workflow (`.github/workflows/ci-cd.yaml`): lint and test, then deploy.

## Development

The development environment is managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

To run the formatting, linting and testing:

```bash
uv run poe all
```
