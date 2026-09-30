"""Azure Functions entry point.

Wraps the existing FastAPI app (dehumidifier_controller.main:app) via ASGI so
all routes (/health, /simulate, /optimisation) are served unchanged behind a
single HTTP-triggered function. Auth is enforced at the function level (a
function key is required on every request) since this plan drops the
internal-only ingress that Container Apps provided for free.
"""

import azure.functions as func

from dehumidifier_controller.main import app

asgi_app = func.AsgiFunctionApp(app=app, http_auth_level=func.AuthLevel.FUNCTION)
