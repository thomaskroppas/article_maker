"""Outline и вложенные схемы — ТЗ 13.4."""

from __future__ import annotations

from typing import List

from .base import SchemaBase


class SectionSpec(SchemaBase):
    section_id: str
    title: str
    level: str = "H2"  # H2 | H3
    purpose: str = ""
    target_word_count: int = 200
    keywords: List[str] = []
    must_cover: List[str] = []


class FaqSection(SchemaBase):
    enabled: bool = False
    questions: List[str] = []


class Outline(SchemaBase):
    h1: str = ""
    sections: List[SectionSpec]
    faq_section: FaqSection = FaqSection()
