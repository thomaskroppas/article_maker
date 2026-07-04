"""Celery-приложение: задача run_pipeline + восстановление осиротевших прогонов.

Инициализация Celery на Redis-брокере, health-задача ping, run_pipeline (§5.3, §6)
и хук worker_ready, который на старте воркера переводит зависшие прогоны в failed
(доделка T-7 — обработка осиротевших пайплайнов).
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_ready

from .config import get_settings

logger = logging.getLogger(__name__)

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


@worker_ready.connect
def _recover_orphans_on_start(**_kwargs) -> None:
    """При старте воркера перевести осиротевшие прогоны в failed (§6.8.1, T-7).

    Задачи, погибшие при перезапуске/падении воркера, оставляют статьи в
    нетерминальных статусах; здесь они закрываются, освобождая «активные» слоты.
    Активные (по инспекции брокера) задачи не трогаются.
    """
    import redis as redis_lib

    from .db.session import SessionLocal
    from .orchestrator.recovery import get_active_article_ids, recover_orphaned_pipelines

    cfg = get_settings()
    active = get_active_article_ids(celery_app) or set()
    try:
        redis_client = redis_lib.Redis.from_url(cfg.redis_url, decode_responses=True)
        recovered = recover_orphaned_pipelines(
            SessionLocal, active, redis_client=redis_client
        )
        if recovered:
            logger.warning(
                "Восстановление: %d осиротевших прогонов → failed: %s",
                len(recovered),
                ", ".join(recovered),
            )
    except Exception as exc:  # noqa: BLE001 — не валим старт воркера из-за recovery
        logger.error("Ошибка восстановления осиротевших прогонов: %s", exc)


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
