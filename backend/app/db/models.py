"""SQLAlchemy 2.0 модели всех таблиц — ТЗ раздел 12 + app_settings (10.10).

DDL-источник истины — Alembic-миграции; модели держатся с ними в соответствии
(индексы заданы в __table_args__ с именами из §12).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_NOW = text("now()")


class Niche(Base):
    __tablename__ = "niches"

    niche_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Archetype(Base):
    __tablename__ = "archetypes"

    archetype_id: Mapped[str] = mapped_column(Text, primary_key=True)
    niche_id: Mapped[str] = mapped_column(
        Text, ForeignKey("niches.niche_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    intent_triggers: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class Site(Base):
    __tablename__ = "sites"

    domain: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    niche_id: Mapped[str | None] = mapped_column(Text, ForeignKey("niches.niche_id"))
    is_test: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    wordpress_url: Mapped[str | None] = mapped_column(Text)
    wordpress_user: Mapped[str | None] = mapped_column(Text)
    wordpress_password: Mapped[str | None] = mapped_column(Text)  # зашифровано
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )


class StyleReference(Base):
    __tablename__ = "style_references"

    reference_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    geo: Mapped[str] = mapped_column(Text, nullable=False)
    niche_tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    notes: Mapped[str | None] = mapped_column(Text)
    reference_text: Mapped[str | None] = mapped_column(Text)
    extracted_style: Mapped[str | None] = mapped_column(Text)
    extracted_tone: Mapped[str | None] = mapped_column(Text)
    extracted_age_image: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )

    __table_args__ = (
        Index("idx_style_references_language", "language"),
        Index("idx_style_references_niche_tags", "niche_tags", postgresql_using="gin"),
    )


class Author(Base):
    __tablename__ = "authors"

    author_id: Mapped[str] = mapped_column(Text, primary_key=True)
    site_domain: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.domain"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    character: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(Text)
    age_image: Mapped[str | None] = mapped_column(Text)
    niche_id: Mapped[str | None] = mapped_column(Text, ForeignKey("niches.niche_id"))
    reference_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("style_references.reference_id")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )

    __table_args__ = (Index("idx_authors_site_domain", "site_domain"),)


class Article(Base):
    __tablename__ = "articles"

    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    site_domain: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.domain"), nullable=False
    )
    author_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("authors.author_id")
    )
    archetype_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("archetypes.archetype_id")
    )
    title: Mapped[str | None] = mapped_column(Text)
    main_keyword: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # ArticleStatus
    qa_status: Mapped[str | None] = mapped_column(Text)
    qa_score: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(
        Numeric(10, 6), server_default=text("0")
    )
    generation_time_seconds: Mapped[int | None] = mapped_column(Integer)
    input_data: Mapped[dict | None] = mapped_column(JSONB)  # ArticleInput
    started_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )

    __table_args__ = (
        Index("idx_articles_site_domain", "site_domain"),
        Index("idx_articles_created_at", text("created_at DESC")),
        Index("idx_articles_status", "status"),
    )


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.article_id", ondelete="CASCADE"),
    )
    step_name: Mapped[str] = mapped_column(Text, nullable=False)
    step_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # PipelineStepStatus
    started_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))

    __table_args__ = (Index("idx_pipeline_steps_article_id", "article_id"),)


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.article_id", ondelete="CASCADE"),
    )
    section_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    iterations: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    word_count: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))

    __table_args__ = (Index("idx_sections_article_id", "article_id"),)


class ArchetypePick(Base):
    __tablename__ = "archetype_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.article_id", ondelete="CASCADE"),
    )
    suggested_archetype_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("archetypes.archetype_id")
    )
    chosen_archetype_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("archetypes.archetype_id")
    )
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    niche_id: Mapped[str | None] = mapped_column(Text, ForeignKey("niches.niche_id"))
    intent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )


class FactCheckResultRow(Base):
    __tablename__ = "fact_check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.article_id", ondelete="CASCADE"),
    )
    total_statements: Mapped[int | None] = mapped_column(Integer)
    verified: Mapped[int | None] = mapped_column(Integer)
    mismatches: Mapped[int | None] = mapped_column(Integer)
    uncertain: Mapped[int | None] = mapped_column(Integer)
    results_json: Mapped[dict | None] = mapped_column(JSONB)  # FactCheckReport
    checked_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )

    __table_args__ = (Index("idx_fact_check_article_id", "article_id"),)


class AppSetting(Base):
    """Настройки приложения — ТЗ 10.10 (value зашифровано Fernet, приоритет БД → .env)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_NOW
    )
