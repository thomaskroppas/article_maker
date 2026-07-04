from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class KeywordsBlock(BaseModel):
    main: str = ""
    secondary: List[str] = []


class WordCountRange(BaseModel):
    min: int = 0
    max: int = 0


class DataHandlingRules(BaseModel):
    avoid_exact_dates:       bool = False
    use_approximate_language: bool = False


class Brief(BaseModel):
    goal:               str = ""
    search_intent:      str = "informational"
    target_audience:    str = ""
    content_archetype:  str = "guide"
    tone:               str = "neutral_informational"
    style_requirements: List[str] = []
    must_cover:         List[str] = []
    must_not_cover:     List[str] = []
    structure_guidelines: List[str] = []
    word_count_target:  int = 1200
    word_count_range:   WordCountRange = WordCountRange()
    keywords:           KeywordsBlock = KeywordsBlock()
    lsi_keywords:       List[str] = []
    required_elements:  List[str] = []
    forbidden_words:    List[str] = []
    data_handling_rules: DataHandlingRules = DataHandlingRules()

    # Сырой markdown-текст ТЗ от агента
    raw_brief: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()
