from celery import Celery
from app.core.config import settings

celery = Celery(
    "podium",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_track_started=True,
    result_expires=3600,
)
