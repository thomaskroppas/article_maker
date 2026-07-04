"""T-3: модели и enum статусов (без БД)."""

from __future__ import annotations

from app.db.base import Base
from app.db import models  # noqa: F401 — регистрирует таблицы
from app.db.enums import ArticleStatus, PipelineStepStatus, TERMINAL_STATUSES

EXPECTED_TABLES = {
    "niches",
    "archetypes",
    "sites",
    "style_references",
    "authors",
    "articles",
    "pipeline_steps",
    "sections",
    "archetype_picks",
    "fact_check_results",
    "app_settings",
}

# Приложение C — все статусы статьи.
EXPECTED_STATUSES = {
    "created",
    "input_validated",
    "serp_done",
    "competitor_analysis_done",
    "brief_done",
    "outline_done",
    "sections_in_progress",
    "draft_ready",
    "images_done",
    "sources_done",
    "fact_check_done",
    "qa_done",
    "completed",
    "ready_for_manual_review",
    "ready_for_manual_review_with_warnings",
    "failed",
    "stopped_by_user",
    "review_timeout",
}


def test_all_tables_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_article_statuses_match_appendix_c():
    assert {s.value for s in ArticleStatus} == EXPECTED_STATUSES


def test_terminal_statuses():
    assert {s.value for s in TERMINAL_STATUSES} == {
        "completed",
        "ready_for_manual_review",
        "ready_for_manual_review_with_warnings",
        "failed",
        "stopped_by_user",
        "review_timeout",
    }


def test_pipeline_step_statuses():
    assert {s.value for s in PipelineStepStatus} == {
        "running",
        "done",
        "failed",
        "skipped_cache",
    }


def test_cascade_on_child_tables():
    # pipeline_steps/sections/... удаляются каскадно при удалении статьи (ТЗ 12.1.7+).
    for tbl in ("pipeline_steps", "sections", "archetype_picks", "fact_check_results"):
        fks = [
            fk
            for fk in Base.metadata.tables[tbl].foreign_keys
            if fk.column.table.name == "articles"
        ]
        assert fks, f"{tbl}: нет FK на articles"
        assert all(fk.ondelete == "CASCADE" for fk in fks), f"{tbl}: ondelete != CASCADE"
