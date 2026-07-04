"""
Загрузка и рендеринг промптов из файлов.
"""
import logging
from pathlib import Path
from string import Template
from app.config.prompt_settings import PROMPT_REGISTRY

logger = logging.getLogger(__name__)


def load_prompt(agent_name: str) -> str:
    path: Path = PROMPT_REGISTRY.get(agent_name)
    if not path or not path.exists():
        raise FileNotFoundError(f"Промпт не найден: {agent_name} → {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(agent_name: str, variables: dict) -> str:
    """
    Загружает промпт и подставляет переменные.
    Использует $var или ${var} синтаксис.
    """
    template_text = load_prompt(agent_name)
    try:
        return Template(template_text).safe_substitute(variables)
    except Exception as e:
        logger.error(f"Ошибка рендеринга промпта {agent_name}: {e}")
        raise
