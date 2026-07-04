"""Дедупликация точек роста — FR-18 (ТЗ §3.18).

content_gaps фильтруются от тех, чей title уже присутствует среди outline.sections
(по нормализованному совпадению). Используется при формировании review-панели.
"""

from __future__ import annotations

from ..schemas import ContentGap


def _norm(title: str) -> str:
    return " ".join(title.lower().split())


def filter_content_gaps(
    gaps: list[ContentGap], section_titles: list[str]
) -> list[ContentGap]:
    present = {_norm(t) for t in section_titles}
    return [g for g in gaps if _norm(g.title) not in present]
