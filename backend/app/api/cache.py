"""Cache management API — ТЗ §11.2.8."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends

from .deps import require_auth

router = APIRouter(prefix="/api/cache", tags=["cache"], dependencies=[Depends(require_auth)])

_DATA = lambda: Path(os.environ.get("DATA_DIR", "data"))  # noqa: E731

_TARGETS = {
    "serp": lambda: _DATA() / "serp_cache",
    "agent": lambda: _DATA() / "agent_cache",
    "image_keys": lambda: _DATA() / "image_keys_cache.json",
    "translation": lambda: _DATA() / "translation_cache.json",
    "wiki": lambda: _DATA() / "wiki_cache",
}


def _clear(path: Path):
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


@router.delete("/{cache_type}", status_code=204)
def clear_cache(cache_type: str):
    target = _TARGETS.get(cache_type)
    if target:
        _clear(target())
