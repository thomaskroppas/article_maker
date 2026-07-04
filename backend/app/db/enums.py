"""Перечисления статусов.

Статусы статьи — по ТЗ Приложение C. В БД колонка `articles.status` — TEXT
(схема §12 не меняется); этот enum — контракт допустимых значений в коде.
"""

from __future__ import annotations

from enum import Enum


class ArticleStatus(str, Enum):
    # прогресс пайплайна (Приложение C)
    CREATED = "created"
    INPUT_VALIDATED = "input_validated"
    SERP_DONE = "serp_done"
    COMPETITOR_ANALYSIS_DONE = "competitor_analysis_done"
    BRIEF_DONE = "brief_done"
    OUTLINE_DONE = "outline_done"
    SECTIONS_IN_PROGRESS = "sections_in_progress"
    DRAFT_READY = "draft_ready"
    IMAGES_DONE = "images_done"
    SOURCES_DONE = "sources_done"
    FACT_CHECK_DONE = "fact_check_done"
    QA_DONE = "qa_done"
    # терминальные
    COMPLETED = "completed"
    READY_FOR_MANUAL_REVIEW = "ready_for_manual_review"
    READY_FOR_MANUAL_REVIEW_WITH_WARNINGS = "ready_for_manual_review_with_warnings"
    FAILED = "failed"
    STOPPED_BY_USER = "stopped_by_user"
    REVIEW_TIMEOUT = "review_timeout"


TERMINAL_STATUSES = frozenset(
    {
        ArticleStatus.COMPLETED,
        ArticleStatus.READY_FOR_MANUAL_REVIEW,
        ArticleStatus.READY_FOR_MANUAL_REVIEW_WITH_WARNINGS,
        ArticleStatus.FAILED,
        ArticleStatus.STOPPED_BY_USER,
        ArticleStatus.REVIEW_TIMEOUT,
    }
)


class PipelineStepStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED_CACHE = "skipped_cache"
