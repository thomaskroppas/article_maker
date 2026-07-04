"""
Кеш SERP-данных.
Ключ кеша: md5(keyword + language + geo)
Хранится в data/serp_cache/{hash}.json
"""
import hashlib
import json
import logging
from pathlib import Path
from app.config.settings import DATA_DIR

logger = logging.getLogger(__name__)
CACHE_DIR = DATA_DIR / "serp_cache"


def _cache_key(query: str, language: str, geo: str) -> str:
    raw = f"{query.strip().lower()}|{language}|{geo.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def get_cached(query: str, language: str, geo: str) -> dict | None:
    path = _cache_path(_cache_key(query, language, geo))
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"SERP: загружен кеш для '{query}'")
            return data
        except Exception as e:
            logger.warning(f"SERP кеш повреждён: {e}")
    return None


def save_cache(query: str, language: str, geo: str, bundle_dict: dict) -> None:
    path = _cache_path(_cache_key(query, language, geo))
    path.write_text(json.dumps(bundle_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"SERP: кеш сохранён для '{query}' → {path.name}")


def has_cache(query: str, language: str, geo: str) -> bool:
    return _cache_path(_cache_key(query, language, geo)).exists()
