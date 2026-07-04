from __future__ import annotations
from typing import List
from pydantic import BaseModel


class WordCountRange(BaseModel):
    min: int = 0
    avg: float = 0.0
    max: int = 0
    per_page: List[int] = []      # объём каждой страницы отдельно


class H2CountRange(BaseModel):
    min: int = 0
    avg: float = 0.0
    max: int = 0
    per_page: List[int] = []      # кол-во H2 каждой страницы отдельно


class CommonH2Title(BaseModel):
    title:     str = ""           # типичное название блока
    frequency: int = 0            # у скольких конкурентов встречается


class ContentGap(BaseModel):
    title:         str = ""    # название точки роста
    description:   str = ""    # краткое описание что добавить
    after_section: str = ""    # после какой секции лучше вставить (название H2 или "в конец")
    word_count:    int = 200   # рекомендуемый объём


class DataSensitivity(BaseModel):
    time_sensitive:    bool = False
    avoid_exact_dates: bool = False


class CompetitorAnalysisReport(BaseModel):
    search_intent:      str = "informational"
    content_type:       str = "guide"
    content_format:     str = "long_read"
    word_count_range:   WordCountRange = WordCountRange()
    h2_count_range:     H2CountRange = H2CountRange()
    common_h2_titles:   List[CommonH2Title] = []
    structure_patterns: List[str] = []
    common_sections:    List[str] = []
    must_have_topics:   List[str] = []
    optional_topics:    List[str] = []
    content_gaps:       List[ContentGap] = []
    tone:               str = "neutral_informational"
    target_audience:    str = ""
    data_sensitivity:   DataSensitivity = DataSensitivity()
    raw_report:         str = ""

    def to_dict(self) -> dict:
        return self.model_dump()
