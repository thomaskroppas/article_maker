"""SerpBundle — результат шага 1 (SERP).

Вне ТЗ раздел 13: §13 SerpBundle не описывает, а snippet в §6.3 иллюстративен.
Структура — по реальным файлам fixtures/serp_bundle_example.json и
reference_article/serp_bundle.json (совпадает с desktop-форматом). Скачивание
страниц и readability дают `pages`; агрегаты — `aggregated`.
"""

from __future__ import annotations

from typing import List

from .base import SchemaBase


class HeadingsData(SchemaBase):
    h1: List[str] = []
    h2: List[str] = []
    h3: List[str] = []


class PageData(SchemaBase):
    url: str
    title: str = ""
    word_count: int = 0
    headings: HeadingsData = HeadingsData()
    content: str = ""  # очищенный текст (readability)


class AggregatedData(SchemaBase):
    avg_word_count: float = 0.0
    min_word_count: int = 0
    max_word_count: int = 0
    common_headings: List[str] = []
    lsi_terms: List[str] = []


class SerpBundle(SchemaBase):
    query: str
    language: str
    geo: str
    urls: List[str] = []
    pages: List[PageData] = []
    aggregated: AggregatedData = AggregatedData()

    # Сырые данные для агентов (CSV-строка и text-блок)
    analysis_csv: str = ""
    contents_txt: str = ""
