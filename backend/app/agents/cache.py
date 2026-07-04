"""Кэш агентов (ТЗ §6.2).

Ключ: {agent}:{article_title.lower()}:{main_keyword.lower()}:{sorted_secondary}.
Кэшируются competitor/lsi/brief/outline. Хранит сырой JSON результата агента.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


def default_agent_cache_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "agent_cache"


class AgentCache:
    def __init__(self, base_dir: str | Path | None = None):
        self.dir = Path(base_dir) if base_dir else default_agent_cache_dir()

    @staticmethod
    def make_key(
        agent: str, article_title: str, main_keyword: str, secondary_keywords: list[str]
    ) -> str:
        sec = ",".join(sorted(secondary_keywords))
        return f"{agent}:{article_title.lower()}:{main_keyword.lower()}:{sec}"

    def _path(self, agent: str, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.dir / agent / f"{h}.json"

    def get(
        self, agent: str, article_title: str, main_keyword: str, secondary: list[str]
    ) -> Optional[Any]:
        p = self._path(agent, self.make_key(agent, article_title, main_keyword, secondary))
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def set(
        self,
        agent: str,
        article_title: str,
        main_keyword: str,
        secondary: list[str],
        data: Any,
    ) -> Path:
        key = self.make_key(agent, article_title, main_keyword, secondary)
        p = self._path(agent, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
