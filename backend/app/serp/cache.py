"""SERP-кэш (ТЗ §6.3): data/serp_cache/<hash>.json.

hash = sha256(main_keyword|geo|language|provider). Кэш обязателен: экономит
кредиты serper.dev и снижает частоту внешних вызовов.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..schemas import SerpBundle


def default_serp_cache_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "serp_cache"


class SerpCache:
    def __init__(self, base_dir: str | Path | None = None):
        self.dir = Path(base_dir) if base_dir else default_serp_cache_dir()

    @staticmethod
    def make_key(main_keyword: str, geo: str, language: str, provider: str) -> str:
        raw = f"{main_keyword.lower()}|{geo}|{language}|{provider}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(
        self, main_keyword: str, geo: str, language: str, provider: str
    ) -> SerpBundle | None:
        p = self.path(self.make_key(main_keyword, geo, language, provider))
        if not p.exists():
            return None
        return SerpBundle.model_validate_json(p.read_text(encoding="utf-8"))

    def set(
        self, main_keyword: str, geo: str, language: str, provider: str, bundle: SerpBundle
    ) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        p = self.path(self.make_key(main_keyword, geo, language, provider))
        p.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        return p
