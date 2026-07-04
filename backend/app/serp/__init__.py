"""Шаг 1 пайплайна — SERP: провайдеры, кэш, извлечение страниц, агрегация."""

from .aggregation import AverageResult, robust_average, trimmed_mean
from .cache import SerpCache
from .extract import download_and_extract, extract_from_html
from .providers import (
    ManualProvider,
    SerpProvider,
    SerpProviderError,
    SerperDevProvider,
    XmlstockProvider,
    build_provider,
)
from .service import SerpConfig, SerpService

__all__ = [
    "trimmed_mean",
    "robust_average",
    "AverageResult",
    "SerpCache",
    "SerpProvider",
    "SerperDevProvider",
    "XmlstockProvider",
    "ManualProvider",
    "SerpProviderError",
    "build_provider",
    "extract_from_html",
    "download_and_extract",
    "SerpService",
    "SerpConfig",
]
