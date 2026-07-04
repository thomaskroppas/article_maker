"""Niches / Archetypes API (только чтение) — ТЗ §11.2.4."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Archetype, Niche
from .deps import get_db, require_auth

router = APIRouter(prefix="/api", tags=["catalog"], dependencies=[Depends(require_auth)])


@router.get("/niches")
def list_niches(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"niche_id": n.niche_id, "name": n.name, "description": n.description}
        for n in db.execute(select(Niche).order_by(Niche.niche_id)).scalars()
    ]


def _arch_dict(a: Archetype) -> dict:
    return {
        "archetype_id": a.archetype_id,
        "niche_id": a.niche_id,
        "name": a.name,
        "description": a.description,
        "intent_triggers": a.intent_triggers or [],
    }


@router.get("/archetypes")
def list_archetypes(db: Session = Depends(get_db), niche_id: str | None = None) -> list[dict]:
    stmt = select(Archetype).order_by(Archetype.archetype_id)
    if niche_id:
        stmt = stmt.where(Archetype.niche_id == niche_id)
    return [_arch_dict(a) for a in db.execute(stmt).scalars()]


@router.get("/archetypes/suggest")
def suggest_archetype(
    db: Session = Depends(get_db),
    article_title: str = "",
    main_keyword: str = "",
    niche_id: str | None = None,
) -> dict:
    stmt = select(Archetype)
    if niche_id:
        stmt = stmt.where(Archetype.niche_id == niche_id)
    candidates = list(db.execute(stmt).scalars())
    if not candidates:
        return {"suggested_archetype_id": None, "alternatives": []}
    return {
        "suggested_archetype_id": candidates[0].archetype_id,
        "alternatives": [_arch_dict(a) for a in candidates[1:6]],
    }
