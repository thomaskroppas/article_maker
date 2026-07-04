"""
Кеш результатов агентов (brief, outline, competitor_analysis).
Ключ — md5(агент + параметры ArticleInput).
Хранится в data/agent_cache/{agent}/{hash}.json

Не кешируются: writer, critic, editor, qa, metadata, archetype_picker —
у них есть зависимости от автора/архетипа/секции, которые могут меняться
между прогонами при одних и тех же параметрах ArticleInput.
"""
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from app.config.settings import DATA_DIR

logger = logging.getLogger(__name__)
CACHE_DIR = DATA_DIR / "agent_cache"

# Какие агенты кешируем
CACHED_AGENTS = {"competitor_analysis_agent", "brief_agent", "outline_agent", "lsi_agent"}


def _key(agent: str, article_input) -> str:
    """
    Ключ кеша — отпечаток параметров запроса. Меняется только при
    реально значимых для агента полях ArticleInput.
    """
    parts = [
        agent,
        (article_input.article_title or "").strip().lower(),
        (article_input.main_keyword or "").strip().lower(),
        "|".join(sorted(s.strip().lower() for s in article_input.secondary_keywords)),
    ]
    raw = "::".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _path(agent: str, key: str) -> Path:
    folder = CACHE_DIR / agent
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{key}.json"


def get(agent: str, article_input) -> Optional[dict]:
    """Возвращает кешированный результат или None."""
    if agent not in CACHED_AGENTS:
        return None
    path = _path(agent, _key(agent, article_input))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info(f"[cache hit] {agent} — пропускаем LLM-вызов")
        return data
    except Exception as e:
        logger.warning(f"[cache] {agent}: повреждён файл — {e}")
        return None


def save(agent: str, article_input, result_dict: dict) -> None:
    """Сохраняет результат агента в кеш."""
    if agent not in CACHED_AGENTS:
        return
    path = _path(agent, _key(agent, article_input))
    try:
        path.write_text(
            json.dumps(result_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[cache save] {agent} → {path.name}")
    except Exception as e:
        logger.warning(f"[cache save] {agent}: ошибка записи — {e}")
