"""Константы пайплайна — ТЗ §6.2.1.

Значения зафиксированы ТЗ (не менять без согласования). Переопределяются через
переменные окружения (§6.2.1: «могут быть переопределены»).
"""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


QA_SCORE_PASS = _int("QA_SCORE_PASS", 85)  # score >= 85 → 'pass'
QA_SCORE_WARN = _int("QA_SCORE_WARN", 70)  # >= 70 → 'pass_with_warnings', иначе 'fail'
CRITIC_PASS_SCORE = _int("CRITIC_PASS_SCORE", 60)  # порог принятия секции критиком
SECTION_MAX_ITERATIONS = _int("SECTION_MAX_ITERATIONS", 3)  # циклов Writer/Editor→Critic
REVIEW_TIMEOUT_HOURS = _int("REVIEW_TIMEOUT_HOURS", 4)  # авто-отмена зависшего ревью
FACT_CHECK_MAX_STATEMENTS = _int("FACT_CHECK_MAX_STATEMENTS", 20)

TOTAL_STEPS = 13  # каноническая нумерация шагов (§6.1)
