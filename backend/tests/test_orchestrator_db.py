"""T-7: DBStatusManager — статусы и шаги в реальной БД (guarded).

Пропускается без DATABASE_URL/недоступной БД. В docker и в песочнице с поднятым
Postgres — выполняется (проверяет запись статусов Приложения C в articles).
"""

from __future__ import annotations

import os
import uuid

import fakeredis
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL не задан"
)


def _skip_if_db_down():
    from sqlalchemy import text

    from app.db.session import engine

    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"БД недоступна: {e}")


def _ai():
    from app.paths import fixtures_dir
    from app.schemas import ArticleInput

    return ArticleInput.model_validate(
        dict(
            article_title="Где находится Байкал",
            main_keyword="байкал где находится",
            secondary_keywords=["байкал дно"],
            language="ru",
            geo="ru",
            intent="informational",
            article_type="informational",
            difficulty="easy",
            style_archetype="expert_clear",
            required_elements=["faq"],
            review_outline=False,
            serp_json_path=str(fixtures_dir() / "serp_bundle_example.json"),
        )
    )


def test_db_status_transitions_persisted():
    _skip_if_db_down()
    from app.db.enums import ArticleStatus
    from app.db.models import Article, PipelineStep, Site
    from app.db.session import SessionLocal
    from app.llm import MockLLMClient
    from app.orchestrator.pipeline import run_pipeline_sync
    from app.orchestrator.status import DBStatusManager
    from app.serp.service import SerpConfig, SerpService

    ai = _ai()
    aid = uuid.UUID(ai.article_id)

    with SessionLocal() as s:
        if s.get(Site, "example.net") is None:
            s.add(Site(domain="example.net", name="Example"))
            s.commit()  # сайт до статьи (FK articles.site_domain → sites)
        s.add(
            Article(
                article_id=aid,
                site_domain="example.net",
                language="ru",
                status=ArticleStatus.CREATED.value,
                input_data=ai.model_dump(mode="json"),
            )
        )
        s.commit()

    try:
        r = fakeredis.FakeStrictRedis(decode_responses=True)
        run_pipeline_sync(
            ai,
            redis_client=r,
            llm=MockLLMClient(),
            serp_service=SerpService(),
            serp_config=SerpConfig(),
            status=DBStatusManager(SessionLocal, ai.article_id),
        )
        with SessionLocal() as s:
            article = s.get(Article, aid)
            assert article.status == ArticleStatus.SECTIONS_IN_PROGRESS.value
            assert article.started_at is not None
            steps = (
                s.query(PipelineStep).filter(PipelineStep.article_id == aid).count()
            )
            assert steps >= 5
    finally:
        with SessionLocal() as s:
            article = s.get(Article, aid)
            if article:
                s.delete(article)  # pipeline_steps удалятся каскадом
                s.commit()
