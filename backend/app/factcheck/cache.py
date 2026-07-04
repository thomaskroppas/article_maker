"""Кэш обращений к Wikipedia/Wikidata — ТЗ §9.4.4 (TTL 30 дней)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_TTL_DAYS = 30


def _default_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "wiki_cache"


class WikiCache:
    def __init__(self, base_dir: str | Path | None = None):
        self.dir = Path(base_dir) if base_dir else _default_dir()

    def _path(self, kind: str, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.dir / kind / f"{h}.json"

    def get(self, kind: str, key: str) -> Optional[Any]:
        p = self._path(kind, key)
        if not p.exists():
            return None
        try:
            wrapped = json.loads(p.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(wrapped["fetched_at"])
            if (datetime.now(timezone.utc) - fetched).days > _TTL_DAYS:
                return None
            return wrapped["value"]
        except Exception:  # noqa: BLE001
            return None

    def set(self, kind: str, key: str, value: Any) -> None:
        p = self._path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {"fetched_at": datetime.now(timezone.utc).isoformat(), "value": value},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
