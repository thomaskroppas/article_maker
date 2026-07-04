"""FastAPI-приложение SEO Pipeline.

T-1: каркас — health-check и CORS. Остальные роутеры (sites, authors,
articles, pipeline, settings, WebSocket) добавляются в последующих задачах.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import analytics, articles, cache, catalog, pipeline, settings_router, sites
from .api import websocket as ws_module
from .config import get_settings

settings = get_settings()

app = FastAPI(
    title="SEO Pipeline API",
    version=__version__,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Health-check: 200, если backend жив (ТЗ 19.4). Без авторизации."""
    return {"status": "ok", "version": __version__}


for _router in (
    settings_router.router,
    pipeline.router,
    articles.router,
    sites.router,
    catalog.router,
    analytics.router,
    cache.router,
    ws_module.router,
):
    app.include_router(_router)
