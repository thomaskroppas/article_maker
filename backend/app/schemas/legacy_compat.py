"""legacy desktop-format compatibility — единственный слой нормализации.

Реальные примеры (`fixtures/`, `reference_article/`) сохранены desktop-версией
и в ряде полей расходятся с ТЗ раздел 13. Схемы §13 объявлены строго по ТЗ
(поля/типы не меняются); здесь собран ВЕСЬ маппинг legacy → §13, который
применяется только на входе (Pydantic `mode="before"`), чтобы реальные файлы
парсились без ошибок.

Выходной контракт пайплайна остаётся строго §13: новая генерация пишет только
поля §13 (legacy-ключи сюда не попадают — см. тест test_output_contract и
docs/LEGACY_FORMAT.md с таблицей соответствий).

ВАЖНО: не размазывать нормализацию по модулям схем — любое новое legacy-правило
добавляется сюда.
"""

from __future__ import annotations

from typing import Any

# Допустимые элементы ArticleInput.required_elements (ТЗ 13.1).
ALLOWED_REQUIRED_ELEMENTS: set[str] = {
    "faq",
    "quick_answer",
    "table",
    "list",
    "conclusion",
    "weaved_sources",
}

# legacy desktop-format compatibility: переименованные элементы.
_REQUIRED_ELEMENT_ALIASES: dict[str, str] = {
    # ТЗ 13.1: sources_block не поддерживается — заменён на weaved_sources.
    "sources_block": "weaved_sources",
}

# legacy desktop-format compatibility: ключи DataSensitivity (ТЗ 13.2).
_DATA_SENSITIVITY_ALIASES: dict[str, str] = {
    "time_sensitive": "has_volatile_data",
}


def _dedup_strip(items: list[Any]) -> list[str]:
    """Очистка списка строк от пустых + дедупликация с сохранением порядка."""
    out: list[str] = []
    for x in items:
        if not isinstance(x, str):
            continue
        s = x.strip()
        if s and s not in out:
            out.append(s)
    return out


def normalize_string_list(value: Any) -> Any:
    """Дедуп + очистка списка строк (ТЗ 13.1: «списки дедуплицируются»)."""
    if value is None:
        return value
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list):
        return _dedup_strip(value)
    return value


def normalize_required_elements(value: Any) -> Any:
    """legacy desktop-format compatibility: sources_block → weaved_sources (+ dedup)."""
    if value is None:
        return value
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return value
    mapped = [
        _REQUIRED_ELEMENT_ALIASES.get(x, x) if isinstance(x, str) else x for x in value
    ]
    return _dedup_strip(mapped)


def normalize_word_count_range(data: Any) -> Any:
    """legacy desktop-format compatibility: avg → avg_trimmed (ТЗ 13.2)."""
    if not isinstance(data, dict):
        return data
    d = dict(data)
    if "avg_trimmed" not in d and "avg" in d:
        d["avg_trimmed"] = d["avg"]
    return d


def normalize_data_sensitivity(data: Any) -> Any:
    """legacy desktop-format compatibility: time_sensitive → has_volatile_data (ТЗ 13.2).

    Legacy-ключ `avoid_exact_dates` на уровне DataSensitivity в §13 отсутствует
    (директива вынесена в Brief.data_handling_rules) — намеренно отбрасывается.
    """
    if not isinstance(data, dict):
        return data
    d = dict(data)
    for legacy, new in _DATA_SENSITIVITY_ALIASES.items():
        if new not in d and legacy in d:
            d[new] = d[legacy]
    return d


def normalize_qa_warnings(value: Any) -> Any:
    """legacy desktop-format compatibility: warnings-список → QAWarnings (ТЗ 13.8).

    Desktop хранил warnings плоским списком строк. §13 требует разбиения на
    critical/medium/minor (FR-16). Legacy-предупреждения не размечены по
    важности → все относим к `medium` (не critical, т.к. fail_reasons отдельно).
    """
    if isinstance(value, list):
        return {
            "critical": [],
            "medium": [str(w) for w in value],
            "minor": [],
        }
    return value
