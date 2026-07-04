from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class SectionSpec(BaseModel):
    section_id:       str
    title:            str
    level:            str = "H2"        # H2 | H3
    purpose:          str = ""
    target_word_count: int = 200
    keywords:         List[str] = []
    must_cover:       List[str] = []


class FaqSection(BaseModel):
    enabled:   bool = False
    questions: List[str] = []


class Outline(BaseModel):
    h1:          str = ""
    sections:    List[SectionSpec] = []
    faq_section: FaqSection = FaqSection()

    def to_dict(self) -> dict:
        return self.model_dump()

    def total_word_count(self) -> int:
        return sum(s.target_word_count for s in self.sections)
