"""Резолвинг каталогов проекта (prompts/ fixtures/ reference_article/).

Работает и локально (дерево репозитория), и в контейнере (каталоги смонтированы
в /app). Приоритет: env-override → поиск вверх по дереву от cwd и от модуля.
"""

from __future__ import annotations

import os
from pathlib import Path


def _search_up(name: str, marker: str) -> Path | None:
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    seen: set[Path] = set()
    for start in starts:
        for d in [start, *start.parents]:
            if d in seen:
                continue
            seen.add(d)
            cand = d / name
            if (cand / marker).exists():
                return cand
    return None


def _resolve(env_var: str, name: str, marker: str) -> Path:
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    found = _search_up(name, marker)
    if found is not None:
        return found
    # запасной вариант — /app/<name> (контейнер) или cwd/<name>
    return Path("/app") / name if Path("/app").exists() else Path.cwd() / name


def prompts_dir() -> Path:
    return _resolve("PROMPTS_DIR", "prompts", "writer_agent/v1.txt")


def fixtures_dir() -> Path:
    return _resolve("FIXTURES_DIR", "fixtures", "serp_bundle_example.json")


def reference_dir() -> Path:
    return _resolve("REFERENCE_DIR", "reference_article", "article.md")
