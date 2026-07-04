"""Celery-приложение (заглушка T-1).

Полная задача `run_pipeline` реализуется в T-7. Здесь — только инициализация
Celery на Redis-брокере и health-задача `ping`, чтобы worker-сервис поднимался
в docker-compose.
"""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "seo_pipeline",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Сохраняем поведение ретраев подключения к брокеру на старте (Celery 6.0+
    # иначе выдаёт CPendingDeprecationWarning).
    broker_connection_retry_on_startup=True,
)

# `celery -A app.worker worker` ищет атрибут `app` или `celery` в модуле.
app = celery_app


@celery_app.task(name="ping")
def ping() -> str:
    """Health-задача worker'а (заглушка до T-7)."""
    return "pong"
