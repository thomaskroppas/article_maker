"""Section pipeline (ТЗ 13.5) и FullDraft (ТЗ 13.6).

Это ВЫХОДНОЙ контракт §13 web-пайплайна. Desktop-артефакты секций
(reference_article/sections/*_draft|review) имеют иной формат и парсятся
отдельными схемами в desktop_artifacts.py (вне §13).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from .base import SchemaBase


class SectionAttempt(SchemaBase):
    section_id: str
    iteration: int
    author: str
    text: str
    summary: Optional[str] = None  # <!-- SUMMARY: ... -->
    tokens_in: int
    tokens_out: int
    cost_usd: float


class CriticFeedback(SchemaBase):
    overall_score: int  # 0-100
    per_criterion: dict
    issues: List[str]
    suggestions: List[str]


class SectionFinal(SchemaBase):
    section_id: str
    title: str = ""
    content: str = ""
    iterations: int = 1


class FullDraft(SchemaBase):
    h1: str = ""
    content_markdown: str = ""
    sections: List[SectionFinal] = Field(default_factory=list)
    word_count: int = 0
    section_count: int = 0
