# humidity-simulator

FastAPI service exposing `/simulate` and `/optimisation`, deployed as an
Azure Functions app (`function_app.py` wraps it via ASGI).

## Local development

```bash
uv sync
docker compose up -d --build   # api on :8000
```

## Testing against the Functions host

```bash
cp local.settings.json.example local.settings.json
uv run poe func-requirements   # regenerates requirements.txt from uv.lock
func start
```

`requirements.txt` is gitignored and generated on demand — `uv.lock` is the
source of truth. CI regenerates it before deploying.
