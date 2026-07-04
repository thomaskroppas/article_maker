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
    """Health-задача worker'а."""
    return "pong"


@celery_app.task(name="run_pipeline")
def run_pipeline(article_id: str) -> dict:
    """Запуск пайплайна генерации статьи (ТЗ §5.3, §6).

    Загружает ArticleInput из БД, строит зависимости из настроек и прогоняет
    оркестратор. LLM — MockLLMClient до T-14 (живые вызовы только там).
    """
    import uuid

    import redis as redis_lib

    from .agents.cache import AgentCache
    from .constants import review_timeout_seconds
    from .db.models import Article
    from .db.session import SessionLocal
    from .llm import MockLLMClient
    from .orchestrator.pipeline import run_pipeline_sync
    from .orchestrator.status import DBStatusManager
    from .schemas import ArticleInput
    from .serp.service import SerpConfig, SerpService

    cfg = get_settings()
    with SessionLocal() as session:
        article = session.get(Article, uuid.UUID(str(article_id)))
        if article is None or not article.input_data:
            return {"article_id": article_id, "error": "article not found"}
        ai = ArticleInput.model_validate(article.input_data)

    redis_client = redis_lib.Redis.from_url(cfg.redis_url, decode_responses=True)
    result = run_pipeline_sync(
        ai,
        redis_client=redis_client,
        llm=MockLLMClient(),
        serp_service=SerpService(),
        serp_config=SerpConfig(
            serp_provider=cfg.serp_provider,
            serper_api_key=cfg.serper_api_key,
            xmlstock_api_url=cfg.xmlstock_api_url,
        ),
        status=DBStatusManager(SessionLocal, article_id),
        agent_cache=AgentCache(),
        review_timeout_seconds=review_timeout_seconds(),
    )
    return {"article_id": article_id, "aborted": result.get("aborted")}
