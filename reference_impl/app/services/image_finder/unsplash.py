"""
Провайдер Unsplash. Использует пул API-ключей с ротацией (round-robin).
Ключи из .env: UNSPLASH_API_KEYS=key1,key2,key3
При 429/403 — пропускаем ключ на час и идём к следующему.
"""
import logging
import os
import time
from typing import Optional, List
import requests

from app.services.image_finder.base import ImageProvider, ImageResult

logger = logging.getLogger(__name__)

_API_URL = "https://api.unsplash.com/search/photos"


class UnsplashProvider(ImageProvider):
    name = "unsplash"

    def __init__(self):
        keys = os.getenv("UNSPLASH_API_KEYS", "").strip()
        self._keys: List[str] = [k.strip() for k in keys.split(",") if k.strip()]
        self._cursor = 0
        self._blocked_until: dict[str, float] = {}  # key -> unix-ts

    def is_available(self) -> bool:
        return bool(self._keys)

    def _next_key(self) -> Optional[str]:
        """Возвращает следующий рабочий ключ (не заблокированный)."""
        if not self._keys:
            return None
        now = time.time()
        for _ in range(len(self._keys)):
            key = self._keys[self._cursor % len(self._keys)]
            self._cursor += 1
            if self._blocked_until.get(key, 0) > now:
                continue
            return key
        return None

    def _block_key(self, key: str, seconds: int = 3600):
        self._blocked_until[key] = time.time() + seconds

    def search_many(self, query: str, language: str = "ru",
                    limit: int = 5) -> list[ImageResult]:
        if not self.is_available():
            return []

        key = self._next_key()
        if key is None:
            logger.info("[unsplash] все ключи временно заблокированы")
            return []

        try:
            resp = requests.get(
                _API_URL,
                params={"query": query, "per_page": str(limit), "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {key}"},
                timeout=10,
            )
            if resp.status_code in (401, 403, 429):
                self._block_key(key)
                logger.warning(f"[unsplash] ключ заблокирован: {resp.status_code}")
                return self.search_many(query, language, limit)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return [
                ImageResult(
                    url=r["urls"]["regular"],
                    source_url=r["links"]["html"],
                    attribution=f"{r['user']['name']} on Unsplash",
                )
                for r in results
            ]
        except Exception as e:
            logger.warning(f"[unsplash] поиск '{query}' упал: {e}")
            return []