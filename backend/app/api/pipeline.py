"""Pipeline API — ТЗ §11.2.6."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.enums import ArticleStatus
from ..db.models import Article, Site
from ..orchestrator.control import PipelineControl
from ..orchestrator.events import events_list_key
from ..schemas import ArticleInput, Outline
from .deps import get_db, require_auth
from .redis_client import get_redis

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"], dependencies=[Depends(require_auth)])


@router.post("/run")
def run_pipeline_endpoint(body: ArticleInput, db: Session = Depends(get_db)) -> dict:
    aid = uuid.UUID(body.article_id)
    # Гарантируем существование сайта (FK articles.site_domain).
    if db.get(Site, body.site_domain) is None:
        db.add(Site(domain=body.site_domain, name=body.site_domain))
        db.commit()
    db.add(
        Article(
            article_id=aid,
            site_domain=body.site_domain,
            author_id=body.author_id,
            title=body.article_title,
            main_keyword=body.main_keyword,
            language=body.language,
            status=ArticleStatus.CREATED.value,
            input_data=body.model_dump(mode="json"),
        )
    )
    db.commit()

    from ..worker import run_pipeline as run_pipeline_task

    run_pipeline_task.delay(str(aid))
    return {"article_id": str(aid), "ws_url": f"/ws/pipeline/{aid}"}


@router.post("/{article_id}/stop", status_code=204)
def stop_pipeline(article_id: str):
    PipelineControl(get_redis(), article_id).request_stop()


@router.post("/{article_id}/resume", status_code=204)
def resume_pipeline(article_id: str, outline: Outline):
    PipelineControl(get_redis(), article_id).confirm_review({"outline": outline.model_dump()})


@router.get("/{article_id}/status")
def pipeline_status(article_id: str, db: Session = Depends(get_db)) -> dict:
    article = db.get(Article, uuid.UUID(article_id))
    if article is None:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    elapsed = None
    if article.started_at:
        end = article.finished_at or article.started_at
        elapsed = int((end - article.started_at).total_seconds())
    return {
        "status": article.status,
        "qa_score": article.qa_score,
        "elapsed_time": elapsed,
        "started_at": article.started_at.isoformat() if article.started_at else None,
        "finished_at": article.finished_at.isoformat() if article.finished_at else None,
    }


@router.get("/{article_id}/events")
def pipeline_events(article_id: str) -> dict:
    raw = get_redis().lrange(events_list_key(article_id), 0, -1)
    return {"events": [json.loads(x) for x in raw]}
