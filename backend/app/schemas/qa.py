"""QAResult и вложенные схемы — ТЗ 13.8."""

from __future__ import annotations

from typing import List

from pydantic import model_validator

from .base import SchemaBase
from .legacy_compat import normalize_qa_warnings


class CriteriaScores(SchemaBase):
    brief_alignment: float = 0.0
    intent_coverage: float = 0.0
    keyword_usage: float = 0.0
    lsi_coverage: float = 0.0
    factuality: float = 0.0
    structure: float = 0.0
    readability: float = 0.0
    length_control: float = 0.0
    completeness: float = 0.0


class QAWarnings(SchemaBase):
    critical: List[str] = []
    medium: List[str] = []
    minor: List[str] = []


class QAResult(SchemaBase):
    status: str  # 'pass' | 'pass_with_warnings' | 'fail'
    score: int  # 0-100
    criteria_scores: CriteriaScores
    warnings: QAWarnings
    fail_reasons: List[str]
    recommendation: str

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        # legacy desktop-format compatibility: warnings-список -> QAWarnings
        if isinstance(data, dict) and "warnings" in data:
            data = dict(data)
            data["warnings"] = normalize_qa_warnings(data["warnings"])
        return data
