"""Загрузка и рендеринг промптов `prompts/<agent>/<file>` через string.Template.

ТЗ §20.2–20.4. Промпты используются как есть (не редактируются). Подстановка —
`string.Template.safe_substitute`: это снимает риск 22.8 (символ `$` в тексте
промпта не как переменная) — safe_substitute не падает на невалидных/пропущенных
плейсхолдерах (в отличие от substitute), оставляя их как есть.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from ..paths import prompts_dir

PROMPT_VERSION = "v1"

# Имя файла промпта по агенту. По умолчанию — v1.txt; image_keys_agent поставлен
# как v1_reference_from_code.txt (референс, извлечённый из desktop-кода).
_PROMPT_FILES: dict[str, str] = {
    "image_keys_agent": "v1_reference_from_code.txt",
}

# 13 агентов с готовыми промптами (ТЗ §20.1). sources_weaver/fact_checker — T-9.
PROMPT_AGENTS: tuple[str, ...] = (
    "competitor_analysis_agent",
    "lsi_agent",
    "brief_agent",
    "outline_agent",
    "writer_agent",
    "critic_agent",
    "editor_agent",
    "faq_writer_agent",
    "final_qa_agent",
    "metadata_agent",
    "archetype_picker_agent",
    "style_extractor_agent",
    "image_keys_agent",
)


def prompt_path(agent_name: str) -> Path:
    filename = _PROMPT_FILES.get(agent_name, f"{PROMPT_VERSION}.txt")
    return prompts_dir() / agent_name / filename


def load_prompt(agent_name: str) -> str:
    path = prompt_path(agent_name)
    if not path.exists():
        raise FileNotFoundError(f"Промпт не найден: {agent_name} → {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(agent_name: str, variables: dict) -> str:
    """Загрузить промпт и подставить переменные ($var / ${var}).

    safe_substitute не бросает на литеральный `$` и на отсутствующих переменных.
    """
    template_text = load_prompt(agent_name)
    return Template(template_text).safe_substitute(variables)
