"""FactCheckReport — ТЗ 13.7 / 9.3."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .base import SchemaBase


class FactStatement(SchemaBase):
    text: str  # исходное предложение из статьи
    type: str  # "numeric" | "date" | "location" | "name"
    subject: str
    property: Optional[str] = None
    value_in_article: str


class FactCheckResult(SchemaBase):
    statement: FactStatement
    status: str  # "verified" | "mismatch" | "uncertain"
    external_value: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    confidence: float  # 0.0 - 1.0


class FactCheckReport(SchemaBase):
    total_statements: int
    verified: int
    mismatches: int
    uncertain: int
    results: List[FactCheckResult]
    checked_at: datetime
