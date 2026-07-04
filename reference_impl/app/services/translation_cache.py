"""
Кеш переводов поисковых запросов (русский → английский).
Хранится в data/translation_cache.json — плоский dict «запрос → перевод».
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from app.config.settings import DATA_DIR

logger = logging.getLogger(__name__)
_CACHE_PATH = DATA_DIR / "translation_cache.json"


def _load() -> Dict[str, str]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[translation_cache] чтение упало: {e}")
        return {}


def _save(data: Dict[str, str]) -> None:
    try:
        _CACHE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[translation_cache] запись упала: {e}")


def get(query: str) -> Optional[str]:
    return _load().get(query)


def put(query: str, translation: str) -> None:
    data = _load()
    data[query] = translation
    _save(data)


def put_many(pairs: Dict[str, str]) -> None:
    data = _load()
    data.update(pairs)
    _save(data)
