"""
Провайдер Pixabay. Пул ключей в PIXABAY_API_KEYS.
Лимит 100/мин на ключ — щедрее Unsplash.
"""
import logging
import os
import time
from typing import Optional, List
import requests

from app.services.image_finder.base import ImageProvider, ImageResult

logger = logging.getLogger(__name__)

_API_URL = "https://pixabay.com/api/"


class PixabayProvider(ImageProvider):
    name = "pixabay"

    def __init__(self):
        keys = os.getenv("PIXABAY_API_KEYS", "").strip()
        self._keys: List[str] = [k.strip() for k in keys.split(",") if k.strip()]
        self._cursor = 0
        self._blocked_until: dict[str, float] = {}

    def is_available(self) -> bool:
        return bool(self._keys)

    def _next_key(self) -> Optional[str]:
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

    def _block_key(self, key: str, seconds: int = 600):
        self._blocked_until[key] = time.time() + seconds

    def search_many(self, query: str, language: str = "ru",
                    limit: int = 5) -> list[ImageResult]:
        if not self.is_available():
            return []

        key = self._next_key()
        if key is None:
            return []

        try:
            resp = requests.get(
                _API_URL,
                params={
                    "key": key,
                    "q": query,
                    "lang": language if language in ("ru","en","de","fr","es","it") else "en",
                    "image_type": "photo",
                    "per_page": str(max(3, limit)),  # pixabay минимум 3
                    "orientation": "horizontal",
                    "safesearch": "true",
                },
                timeout=10,
            )
            if resp.status_code in (401, 403, 429):
                self._block_key(key)
                logger.warning(f"[pixabay] ключ заблокирован: {resp.status_code}")
                return self.search_many(query, language, limit)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            return [
                ImageResult(
                    url=h.get("largeImageURL") or h.get("webformatURL"),
                    source_url=h.get("pageURL", ""),
                    attribution=f"{h.get('user','Pixabay')} on Pixabay",
                )
                for h in hits
                if h.get("largeImageURL") or h.get("webformatURL")
            ]
        except Exception as e:
            logger.warning(f"[pixabay] поиск '{query}' упал: {e}")
            return []