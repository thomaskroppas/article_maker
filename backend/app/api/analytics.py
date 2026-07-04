"""Analytics API — ТЗ §11.2.7."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.enums import ArticleStatus
from ..db.models import Article
from .deps import get_db, require_auth

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_auth)])


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        select(
            func.count(Article.article_id),
            func.avg(Article.qa_score),
            func.coalesce(func.sum(Article.cost_usd), 0),
        )
    ).one()
    return {
        "total": row[0] or 0,
        "avg_qa": round(float(row[1]), 1) if row[1] is not None else None,
        "total_cost": float(row[2] or 0),
    }


@router.get("/by-site")
def by_site(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(
            Article.site_domain,
            func.count(Article.article_id),
            func.avg(Article.qa_score),
            func.coalesce(func.sum(Article.cost_usd), 0),
        ).group_by(Article.site_domain)
    ).all()
    return [
        {"site": r[0], "count": r[1], "avg_qa": round(float(r[2]), 1) if r[2] is not None else None,
         "cost": float(r[3] or 0)}
        for r in rows
    ]


@router.get("/trend")
def trend(db: Session = Depends(get_db)) -> list[dict]:
    week = func.date_trunc("week", Article.created_at)
    rows = db.execute(
        select(week, func.count(Article.article_id), func.avg(Article.qa_score))
        .group_by(week)
        .order_by(week)
    ).all()
    return [
        {"week": r[0].isoformat() if r[0] else None, "count": r[1],
         "avg_qa": round(float(r[2]), 1) if r[2] is not None else None}
        for r in rows
    ]


@router.get("/top-authors")
def top_authors(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Article.author_id, func.count(Article.article_id), func.avg(Article.qa_score))
        .where(Article.author_id.isnot(None))
        .group_by(Article.author_id)
        .order_by(func.count(Article.article_id).desc())
        .limit(10)
    ).all()
    return [
        {"author": r[0], "count": r[1], "avg_qa": round(float(r[2]), 1) if r[2] is not None else None}
        for r in rows
    ]


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["article_id", "site_domain", "status", "qa_score", "cost_usd", "created_at"])
    for a in db.execute(select(Article).order_by(Article.created_at.desc())).scalars():
        w.writerow([str(a.article_id), a.site_domain, a.status, a.qa_score,
                    float(a.cost_usd) if a.cost_usd is not None else "",
                    a.created_at.isoformat() if a.created_at else ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=articles.csv"})
