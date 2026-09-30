"""Azure Functions entry point."""

import azure.functions as func

from dehumidifier_controller.main import app

asgi_app = func.AsgiFunctionApp(app=app, http_auth_level=func.AuthLevel.FUNCTION)
