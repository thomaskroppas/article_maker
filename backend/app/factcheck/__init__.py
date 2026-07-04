"""Шаг 11 — fact-checking: извлечение утверждений + верификация (ТЗ §9)."""

from .cache import WikiCache
from .extraction import FactExtractionAgent
from .verify import compare_numeric, default_lookup, verify_statements

__all__ = [
    "FactExtractionAgent",
    "WikiCache",
    "verify_statements",
    "compare_numeric",
    "default_lookup",
]
