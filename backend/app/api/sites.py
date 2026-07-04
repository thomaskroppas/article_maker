"""Sites / Authors / Style references API — ТЗ §11.2.1–11.2.3."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Article, Author, Site, StyleReference
from ..llm import MockLLMClient
from .deps import get_db, require_auth

router = APIRouter(prefix="/api", tags=["sites"], dependencies=[Depends(require_auth)])


# ─── Sites ───
class SiteIn(BaseModel):
    domain: str
    name: str
    niche_id: str | None = None
    is_test: bool = False
    wordpress_url: str | None = None
    wordpress_user: str | None = None


def _site_dict(s: Site) -> dict:
    return {"domain": s.domain, "name": s.name, "niche_id": s.niche_id, "is_test": s.is_test,
            "wordpress_url": s.wordpress_url, "wordpress_user": s.wordpress_user}


@router.get("/sites")
def list_sites(db: Session = Depends(get_db)) -> list[dict]:
    return [_site_dict(s) for s in db.execute(select(Site).order_by(Site.domain)).scalars()]


@router.post("/sites", status_code=201)
def create_site(body: SiteIn, db: Session = Depends(get_db)) -> dict:
    if db.get(Site, body.domain) is not None:
        raise HTTPException(status_code=409, detail="Сайт уже существует")
    site = Site(**body.model_dump())
    db.add(site)
    db.commit()
    return _site_dict(site)


def _site_or_404(db: Session, domain: str) -> Site:
    s = db.get(Site, domain)
    if s is None:
        raise HTTPException(status_code=404, detail="Сайт не найден")
    return s


@router.get("/sites/{domain}")
def get_site(domain: str, db: Session = Depends(get_db)) -> dict:
    return _site_dict(_site_or_404(db, domain))


@router.put("/sites/{domain}")
def update_site(domain: str, body: SiteIn, db: Session = Depends(get_db)) -> dict:
    s = _site_or_404(db, domain)
    for k, v in body.model_dump(exclude={"domain"}).items():
        setattr(s, k, v)
    db.commit()
    return _site_dict(s)


@router.delete("/sites/{domain}", status_code=204)
def delete_site(domain: str, db: Session = Depends(get_db)):
    db.delete(_site_or_404(db, domain))
    db.commit()


@router.get("/sites/{domain}/stats")
def site_stats(domain: str, db: Session = Depends(get_db)) -> dict:
    _site_or_404(db, domain)
    row = db.execute(
        select(func.count(Article.article_id), func.avg(Article.qa_score),
               func.coalesce(func.sum(Article.cost_usd), 0))
        .where(Article.site_domain == domain)
    ).one()
    return {"count": row[0] or 0, "avg_qa": round(float(row[1]), 1) if row[1] is not None else None,
            "cost": float(row[2] or 0)}


# ─── Authors ───
class AuthorIn(BaseModel):
    name: str
    character: str | None = None
    tone: str | None = None
    age_image: str | None = None
    niche_id: str | None = None
    reference_id: str | None = None


def _author_dict(a: Author) -> dict:
    return {"author_id": a.author_id, "site_domain": a.site_domain, "name": a.name,
            "character": a.character, "tone": a.tone, "age_image": a.age_image,
            "niche_id": a.niche_id, "reference_id": a.reference_id, "is_active": a.is_active}


@router.get("/sites/{domain}/authors")
def list_authors(domain: str, db: Session = Depends(get_db)) -> list[dict]:
    _site_or_404(db, domain)
    stmt = select(Author).where(Author.site_domain == domain, Author.is_active.is_(True))
    return [_author_dict(a) for a in db.execute(stmt).scalars()]


@router.post("/sites/{domain}/authors", status_code=201)
def create_author(domain: str, body: AuthorIn, db: Session = Depends(get_db)) -> dict:
    _site_or_404(db, domain)
    author = Author(author_id=str(uuid.uuid4()), site_domain=domain, **body.model_dump())
    db.add(author)
    db.commit()
    return _author_dict(author)


def _author_or_404(db: Session, author_id: str) -> Author:
    a = db.get(Author, author_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Автор не найден")
    return a


@router.get("/authors/{author_id}")
def get_author(author_id: str, db: Session = Depends(get_db)) -> dict:
    return _author_dict(_author_or_404(db, author_id))


@router.put("/authors/{author_id}")
def update_author(author_id: str, body: AuthorIn, db: Session = Depends(get_db)) -> dict:
    a = _author_or_404(db, author_id)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return _author_dict(a)


@router.delete("/authors/{author_id}", status_code=204)
def delete_author(author_id: str, db: Session = Depends(get_db)):
    _author_or_404(db, author_id).is_active = False  # soft-delete (§11.2.2)
    db.commit()


# ─── Style references ───
class ReferenceIn(BaseModel):
    name: str
    language: str
    geo: str = ""
    niche_tags: list[str] = []
    notes: str = ""
    reference_text: str = ""


class ExtractIn(BaseModel):
    writer_name: str = ""
    language: str = "ru"
    geo: str = ""
    notes: str = ""


def _ref_dict(r: StyleReference) -> dict:
    return {"reference_id": r.reference_id, "name": r.name, "language": r.language, "geo": r.geo,
            "niche_tags": r.niche_tags or [], "extracted_style": r.extracted_style,
            "extracted_tone": r.extracted_tone, "extracted_age_image": r.extracted_age_image,
            "is_active": r.is_active}


def _extract_style(inp: ExtractIn) -> dict:
    from ..agents.style_extractor import StyleExtractorAgent

    return StyleExtractorAgent(MockLLMClient()).run(
        writer_name=inp.writer_name, language=inp.language, geo=inp.geo, notes=inp.notes
    )


@router.get("/references")
def list_references(db: Session = Depends(get_db), language: str | None = None) -> list[dict]:
    stmt = select(StyleReference).where(StyleReference.is_active.is_(True))
    if language:
        stmt = stmt.where(StyleReference.language == language)
    return [_ref_dict(r) for r in db.execute(stmt).scalars()]


@router.post("/references", status_code=201)
def create_reference(body: ReferenceIn, db: Session = Depends(get_db)) -> dict:
    extracted = _extract_style(ExtractIn(writer_name=body.name, language=body.language,
                                         geo=body.geo, notes=body.notes))
    ref = StyleReference(
        reference_id=str(uuid.uuid4()), name=body.name, language=body.language, geo=body.geo,
        niche_tags=body.niche_tags, notes=body.notes, reference_text=body.reference_text,
        extracted_style=extracted["extracted_style"], extracted_tone=extracted["extracted_tone"],
        extracted_age_image=extracted["extracted_age_image"],
    )
    db.add(ref)
    db.commit()
    return _ref_dict(ref)


@router.post("/references/extract")
def extract_reference(body: ExtractIn) -> dict:
    return _extract_style(body)


@router.get("/references/{reference_id}")
def get_reference(reference_id: str, db: Session = Depends(get_db)) -> dict:
    r = db.get(StyleReference, reference_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Референс не найден")
    return _ref_dict(r)


@router.delete("/references/{reference_id}", status_code=204)
def delete_reference(reference_id: str, db: Session = Depends(get_db)):
    r = db.get(StyleReference, reference_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Референс не найден")
    db.delete(r)
    db.commit()
