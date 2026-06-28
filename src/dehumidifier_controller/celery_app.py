import os

from celery import Celery

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "dehumidifier_controller",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["dehumidifier_controller.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
