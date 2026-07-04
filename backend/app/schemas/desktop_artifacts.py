"""Desktop-артефакты секций — ВНЕ ТЗ раздел 13.

reference_article/sections/*_draft|patched|review сохранены desktop-версией в
собственном формате, не совпадающем с §13.5 (SectionAttempt/CriticFeedback).
Эти схемы нужны только чтобы такие legacy-файлы парсились в тестах; web-пайплайн
их НЕ производит — он пишет §13.5 (см. section.py). Соответствие форматов —
docs/LEGACY_FORMAT.md.
"""

from __future__ import annotations

from typing import List

from .base import SchemaBase


class SectionDraftArtifact(SchemaBase):
    """Черновик/патч секции: *_draft.json, *_patched_N.json."""

    section_id: str
    title: str = ""
    content: str = ""
    word_count: int = 0
    iteration: int = 1


class SectionReviewArtifact(SchemaBase):
    """Ревью секции критиком: *_review_N.json."""

    section_id: str
    status: str = ""
    issues: List[str] = []
    fix_instructions: List[str] = []
    iteration: int = 1
