"""Прочие схемы вне ТЗ раздел 13: LSI и данные review-панели.

Структура — по реальным fixtures/lsi_example.json и
fixtures/review_data_example.json.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from .base import SchemaBase


class LSIResult(SchemaBase):
    lsi_keywords: List[str] = []


class ReviewDataInner(SchemaBase):
    # Свёртки для review-панели; внутренние структуры хранятся как есть.
    competitor: dict = Field(default_factory=dict)
    outline: dict = Field(default_factory=dict)
    archetype: dict = Field(default_factory=dict)


class ReviewData(SchemaBase):
    review_data: ReviewDataInner
    suggested_archetype_id: Optional[str] = None
    niche_id: Optional[str] = None
