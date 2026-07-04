"""CompetitorAnalysisReport и вложенные схемы — ТЗ 13.2."""

from __future__ import annotations

from typing import List

from pydantic import model_validator

from .base import SchemaBase
from .legacy_compat import normalize_data_sensitivity, normalize_word_count_range


class WordCountRange(SchemaBase):
    min: int = 0
    avg_trimmed: float = 0.0  # trimmed mean
    max: int = 0
    per_page: List[int] = []

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        # legacy desktop-format compatibility: avg -> avg_trimmed
        return normalize_word_count_range(data)


class CommonH2Title(SchemaBase):
    title: str
    frequency: int


class ContentGap(SchemaBase):
    title: str
    description: str
    after_section: str = ""
    word_count: int = 200


class DataSensitivity(SchemaBase):
    has_volatile_data: bool = False
    has_precise_numbers: bool = False
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        # legacy desktop-format compatibility: time_sensitive -> has_volatile_data
        return normalize_data_sensitivity(data)


class CompetitorAnalysisReport(SchemaBase):
    search_intent: str = "informational"
    content_type: str = "guide"
    word_count_range: WordCountRange
    h2_count_range: WordCountRange
    common_h2_titles: List[CommonH2Title]
    must_have_topics: List[str]
    optional_topics: List[str]
    content_gaps: List[ContentGap]
    data_sensitivity: DataSensitivity = DataSensitivity()
    tone: str = "neutral_informational"
    target_audience: str = ""
    raw_report: str = ""
