"""
Схема serp_bundle — результат SERP-анализа.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class HeadingsData(BaseModel):
    h1: List[str] = []
    h2: List[str] = []
    h3: List[str] = []


class PageData(BaseModel):
    url:        str
    title:      str = ""
    word_count: int = 0
    headings:   HeadingsData = HeadingsData()
    content:    str = ""          # очищенный текст


class AggregatedData(BaseModel):
    avg_word_count:  float = 0.0
    min_word_count:  int   = 0
    max_word_count:  int   = 0
    common_headings: List[str] = []
    lsi_terms:       List[str] = []


class SerpBundle(BaseModel):
    query:      str
    language:   str
    geo:        str
    urls:       List[str] = []
    pages:      List[PageData] = []
    aggregated: AggregatedData = AggregatedData()

    # Сырые данные для агентов (CSV-строка и text-блок)
    analysis_csv:  str = ""
    contents_txt:  str = ""

    def to_dict(self) -> dict:
        return self.model_dump()
