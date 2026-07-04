"""
Кэш ключей для поиска картинок: main_keyword → [10 ключей от LLM].
Хранится в data/image_keys_cache.json — плоский словарь.

См. BACKLOG.md → «Сегментирование кэша» — на больших объёмах статей
кэш будет иметь много пересечений между похожими темами.
"""
import json
import logging
from typing import List, Optional

from app.config.settings import DATA_DIR

logger = logging.getLogger(__name__)
_CACHE_PATH = DATA_DIR / "image_keys_cache.json"


def _load() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[image_keys_cache] чтение упало: {e}")
        return {}


def _save(data: dict) -> None:
    try:
        _CACHE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[image_keys_cache] запись упала: {e}")


def get(main_keyword: str) -> Optional[List[str]]:
    """Возвращает кэшированный список ключей или None."""
    return _load().get((main_keyword or "").lower().strip())


def put(main_keyword: str, keys: List[str]) -> None:
    """Сохраняет список ключей для main_keyword."""
    data = _load()
    data[(main_keyword or "").lower().strip()] = keys
    _save(data)
