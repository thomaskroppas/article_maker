"""Агрегация метрик конкурентов — ТЗ §6.4 (trimmed mean + fallback при малой выборке).

Используется на шаге 2 (competitor) для word_count_range.avg_trimmed и
h2_count_range: значение считается КОДОМ, не LLM.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


def trimmed_mean(values: list[float]) -> float:
    """Среднее без одного минимума и одного максимума (ТЗ §6.4).

    Требует >= 3 значений (иначе усечение не имеет смысла — см. robust_average).
    """
    if len(values) < 3:
        return round(statistics.fmean(values), 2) if values else 0.0
    s = sorted(values)
    trimmed = s[1:-1]
    return round(statistics.fmean(trimmed), 2)


LOW_SAMPLE_WARNING = "Мало конкурентов в SERP, ориентир длины ненадёжен"


@dataclass
class AverageResult:
    avg: float
    method: str  # "trimmed_mean" | "median" | "mean" | "none"
    warning: str | None = None


def robust_average(values: list[float]) -> AverageResult:
    """Устойчивое среднее по числу конкурентов N (ТЗ §6.4):

    - N >= 5 → trimmed mean (без min/max);
    - N = 3..4 → медиана;
    - N = 1..2 → обычное среднее + warning;
    - N = 0 → 0.0 (шаг 1 к этому моменту уже упал бы, см. §6.3/§6.4).
    """
    n = len(values)
    if n == 0:
        return AverageResult(0.0, "none", LOW_SAMPLE_WARNING)
    if n <= 2:
        return AverageResult(round(statistics.fmean(values), 2), "mean", LOW_SAMPLE_WARNING)
    if n <= 4:
        return AverageResult(round(statistics.median(values), 2), "median")
    return AverageResult(trimmed_mean(values), "trimmed_mean")
