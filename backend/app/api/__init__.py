"""REST API-роутеры (ТЗ §11.2)."""

from . import analytics, articles, cache, catalog, pipeline, sites
from . import settings as settings_router

__all__ = [
    "analytics",
    "articles",
    "cache",
    "catalog",
    "pipeline",
    "sites",
    "settings_router",
]
