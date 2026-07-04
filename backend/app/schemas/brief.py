"""Brief и вложенные схемы — ТЗ 13.3."""

from __future__ import annotations

from typing import List

from .base import SchemaBase
from .competitor import WordCountRange


class KeywordsBlock(SchemaBase):
    main: str = ""
    secondary: List[str] = []


class DataHandlingRules(SchemaBase):
    avoid_exact_dates: bool = False
    use_approximate_language: bool = False


class Brief(SchemaBase):
    goal: str = ""
    search_intent: str = "informational"
    target_audience: str = ""
    content_archetype: str = "guide"
    tone: str = "neutral_informational"
    style_requirements: List[str] = []
    must_cover: List[str] = []
    must_not_cover: List[str] = []
    structure_guidelines: List[str] = []
    word_count_target: int = 1200
    word_count_range: WordCountRange
    keywords: KeywordsBlock
    lsi_keywords: List[str] = []
    required_elements: List[str] = []
    forbidden_words: List[str] = []
    data_handling_rules: DataHandlingRules
    raw_brief: str = ""
