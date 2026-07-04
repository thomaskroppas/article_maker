from __future__ import annotations
from typing import List, Optional, Dict
from pydantic import BaseModel


# ─── FullDraft ────────────────────────────────────────────────────────────────

class SectionFinal(BaseModel):
    section_id: str
    title:      str = ""
    content:    str = ""


class FullDraft(BaseModel):
    h1:               str = ""
    content_markdown: str = ""
    sections:         List[SectionFinal] = []
    word_count:       int = 0
    section_count:    int = 0

    def to_dict(self) -> dict:
        return self.model_dump()


# ─── QAResult ─────────────────────────────────────────────────────────────────

class CriteriaScores(BaseModel):
    brief_alignment:  float = 0.0
    intent_coverage:  float = 0.0
    keyword_usage:    float = 0.0
    lsi_coverage:     float = 0.0
    factuality:       float = 0.0
    structure:        float = 0.0
    readability:      float = 0.0
    length_control:   float = 0.0
    completeness:     float = 0.0


class QAResult(BaseModel):
    status:          str = "pass"    # pass | pass_with_warnings | fail
    score:           int = 0
    criteria_scores: CriteriaScores = CriteriaScores()
    warnings:        List[str] = []
    fail_reasons:    List[str] = []
    recommendation:  str = ""

    def to_dict(self) -> dict:
        return self.model_dump()


# ─── FinalPackage ─────────────────────────────────────────────────────────────

class FaqItem(BaseModel):
    question: str
    answer:   str


class SchemaBlock(BaseModel):
    type: str = "FAQPage"
    data: dict = {}


class FinalPackage(BaseModel):
    model_config = {"populate_by_name": True}

    article_id:       str = ""   # ID статьи — для нахождения папки
    slug:             str = ""
    meta_title:       str = ""
    meta_description: str = ""
    article_markdown: str = ""
    faq:              List[FaqItem] = []
    schema_data:      SchemaBlock = SchemaBlock()
    category:         str = ""
    tags:             List[str] = []
    internal_links_suggestions: List[str] = []

    def to_dict(self) -> dict:
        return self.model_dump()
