"""Сохранение промпта и ответа LLM на диск (ТЗ §6.2).

Артефакты кладутся рядом с прочими файлами статьи:
`data/articles/<dir>/prompts/<agent><suffix>_{prompt,response}.txt`
(формат совпадает с reference_article/prompts/).
"""

from __future__ import annotations

from pathlib import Path


def save_llm_interaction(
    target_dir: str | Path,
    agent_name: str,
    prompt: str,
    response: str,
    *,
    suffix: str = "",
) -> Path:
    d = Path(target_dir)
    d.mkdir(parents=True, exist_ok=True)
    base = f"{agent_name}{suffix}"
    (d / f"{base}_prompt.txt").write_text(prompt, encoding="utf-8")
    (d / f"{base}_response.txt").write_text(response, encoding="utf-8")
    return d
