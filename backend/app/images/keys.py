"""image_keys_agent — 10 английских ключей для поиска картинок (ТЗ §7.3.12).

Кэшируется по main_keyword (§6.11). Ключи всегда на английском — Unsplash понимает
только английский (§8.2.5).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ..agents.base import BaseAgent


def _default_cache_path() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "image_keys_cache.json"


class ImageKeysCache:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else _default_cache_path()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def get(self, main_keyword: str) -> Optional[list[str]]:
        return self._load().get(main_keyword.lower())

    def set(self, main_keyword: str, keys: list[str]) -> None:
        data = self._load()
        data[main_keyword.lower()] = keys
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _normalize_keys(parsed) -> list[str]:
    if isinstance(parsed, dict):
        parsed = parsed.get("keys") or parsed.get("image_keys") or []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for x in parsed:
        s = str(x).strip()
        if s and s.lower() not in {o.lower() for o in out}:
            out.append(s)
    return out[:10]


class ImageKeysAgent(BaseAgent):
    agent_name = "image_keys_agent"

    def __init__(self, llm, cache: Optional[ImageKeysCache] = None):
        super().__init__(llm)
        self.cache = cache

    def run(self, article_input) -> list[str]:
        ai = article_input
        if self.cache is not None:
            cached = self.cache.get(ai.main_keyword)
            if cached:
                return cached
        resp = self._call(
            {
                "article_title": ai.article_title,
                "queries_list": ", ".join([ai.main_keyword, *ai.secondary_keywords]),
            }
        )
        keys = _normalize_keys(self._parse_json(resp.text))
        if self.cache is not None and keys:
            self.cache.set(ai.main_keyword, keys)
        return keys
