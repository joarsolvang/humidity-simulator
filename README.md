# humidity-simulator

FastAPI service exposing `/simulate` and `/optimisation`. Runs as an Azure
Functions app (Flex Consumption) in production, wrapped via ASGI in
`function_app.py`.

## Local development

```bash
uv sync
docker compose up -d --build   # api on :8000
```

Or run the FastAPI app directly without Docker:

```bash
uv run uvicorn dehumidifier_controller.main:app --reload
```

## Testing against the real Azure Functions host

The FastAPI routes themselves are covered by `poe test` (against plain
uvicorn via Docker). To sanity-check the Functions-specific packaging
(the ASGI wrapper, `host.json`, auth level) before deploying, use the
[Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local):

```bash
cp local.settings.json.example local.settings.json
uv run poe func-requirements   # regenerates requirements.txt from uv.lock
func start
```

`requirements.txt` is generated on demand (gitignored) — `uv.lock` remains
the source of truth for dependencies. Regenerate it before `func start` or
before a manual `func azure functionapp publish`; CI regenerates it
automatically as part of the deploy job.
