"""Articles API — ТЗ §11.2.5."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Article
from .deps import get_db, require_auth

router = APIRouter(prefix="/api/articles", tags=["articles"], dependencies=[Depends(require_auth)])


def _article_dir(article_id: str) -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "articles" / str(article_id)


def _to_dict(a: Article) -> dict:
    return {
        "article_id": str(a.article_id),
        "site_domain": a.site_domain,
        "title": a.title,
        "main_keyword": a.main_keyword,
        "language": a.language,
        "status": a.status,
        "qa_status": a.qa_status,
        "qa_score": a.qa_score,
        "cost_usd": float(a.cost_usd) if a.cost_usd is not None else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
def list_articles(
    db: Session = Depends(get_db),
    site: str | None = None,
    status: str | None = None,
    min_score: int | None = None,
    limit: int = Query(50, le=200),
) -> list[dict]:
    stmt = select(Article).order_by(Article.created_at.desc()).limit(limit)
    if site:
        stmt = stmt.where(Article.site_domain == site)
    if status:
        stmt = stmt.where(Article.status == status)
    if min_score is not None:
        stmt = stmt.where(Article.qa_score >= min_score)
    return [_to_dict(a) for a in db.execute(stmt).scalars()]


def _get_or_404(db: Session, article_id: str) -> Article:
    a = db.get(Article, uuid.UUID(article_id))
    if a is None:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return a


@router.get("/{article_id}")
def get_article(article_id: str, db: Session = Depends(get_db)) -> dict:
    return _to_dict(_get_or_404(db, article_id))


@router.get("/{article_id}/result")
def get_result(article_id: str, db: Session = Depends(get_db)) -> dict:
    _get_or_404(db, article_id)
    d = _article_dir(article_id)

    def _load(name):
        p = d / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    final_package = _load("final_package.json")
    if final_package is None:
        raise HTTPException(status_code=404, detail="Результат ещё не готов")
    images = [f"images/{p.name}" for p in sorted((d / "images").glob("*.webp"))] if (d / "images").exists() else []
    return {
        "qa_result": _load("qa_result.json"),
        "final_package": final_package,
        "article_markdown": final_package.get("article_markdown", ""),
        "images_urls": images,
    }


@router.get("/{article_id}/archive")
def archive_article(article_id: str, db: Session = Depends(get_db)):
    _get_or_404(db, article_id)
    d = _article_dir(article_id)
    if not d.exists():
        raise HTTPException(status_code=404, detail="Артефакты не найдены")
    zip_base = str(d) + "_archive"
    shutil.make_archive(zip_base, "zip", root_dir=str(d))
    return FileResponse(zip_base + ".zip", media_type="application/zip", filename=f"{article_id}.zip")


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: str, db: Session = Depends(get_db)):
    a = _get_or_404(db, article_id)
    db.delete(a)  # каскад: pipeline_steps/sections/archetype_picks/fact_check_results
    db.commit()
    shutil.rmtree(_article_dir(article_id), ignore_errors=True)  # и папка на диске
