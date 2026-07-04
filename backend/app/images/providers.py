"""Провайдеры картинок с ротацией ключей при 429 — ТЗ §6.11, §8.2.5, §14.3–14.5.

Порядок в пайплайне: Pixabay → Unsplash → Wikimedia. HTTP инъектируется
(в тестах живые вызовы не выполняются).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

PIXABAY_URL = "https://pixabay.com/api/"
UNSPLASH_URL = "https://api.unsplash.com/search/photos"
WIKIMEDIA_URL = "https://commons.wikimedia.org/w/api.php"


@dataclass
class ImageHit:
    url: str
    source_url: str
    provider: str
    alt: str = ""


def _default_get(url, *, headers=None, params=None, timeout=20):
    import requests

    return requests.get(url, headers=headers, params=params, timeout=timeout)


class ImageProvider(ABC):
    name: str = ""

    def is_available(self) -> bool:
        return True

    @abstractmethod
    def search(self, query: str, lang: str) -> Optional[ImageHit]: ...


class _KeyedProvider(ImageProvider):
    """Общая логика ротации ключей при HTTP 429."""

    def __init__(self, keys: list[str], http_get: Optional[Callable] = None):
        self.keys = [k for k in (keys or []) if k]
        self.idx = 0
        self._get = http_get or _default_get

    def is_available(self) -> bool:
        return bool(self.keys)

    @property
    def current_key(self) -> str:
        return self.keys[self.idx]

    def _rotate(self) -> None:
        if self.keys:
            self.idx = (self.idx + 1) % len(self.keys)


class PixabayProvider(_KeyedProvider):
    name = "pixabay"

    def search(self, query: str, lang: str) -> Optional[ImageHit]:
        if not self.keys:
            return None
        for _ in range(len(self.keys)):
            resp = self._get(
                PIXABAY_URL,
                params={
                    "key": self.current_key,
                    "q": query,
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "min_width": 1280,
                    "lang": lang,
                },
            )
            if getattr(resp, "status_code", 200) == 429:
                self._rotate()  # ротация ключа при лимите
                continue
            if resp.status_code != 200:
                return None
            hits = (resp.json() or {}).get("hits") or []
            if not hits:
                return None
            h = hits[0]
            return ImageHit(
                url=h.get("largeImageURL") or h.get("webformatURL", ""),
                source_url=h.get("pageURL", ""),
                provider=self.name,
                alt=h.get("tags", ""),
            )
        return None


class UnsplashProvider(_KeyedProvider):
    name = "unsplash"

    def search(self, query: str, lang: str) -> Optional[ImageHit]:
        if not self.keys:
            return None
        for _ in range(len(self.keys)):
            resp = self._get(
                UNSPLASH_URL,
                headers={"Authorization": f"Client-ID {self.current_key}"},
                params={"query": query, "orientation": "landscape", "per_page": 1},
            )
            if getattr(resp, "status_code", 200) == 429:
                self._rotate()
                continue
            if resp.status_code != 200:
                return None
            results = (resp.json() or {}).get("results") or []
            if not results:
                return None
            r = results[0]
            return ImageHit(
                url=r.get("urls", {}).get("regular", ""),
                source_url=r.get("links", {}).get("html", ""),
                provider=self.name,
                alt=r.get("alt_description") or "",
            )
        return None


class WikimediaProvider(ImageProvider):
    name = "wikimedia"

    def __init__(self, http_get: Optional[Callable] = None):
        self._get = http_get or _default_get

    def search(self, query: str, lang: str) -> Optional[ImageHit]:
        resp = self._get(
            WIKIMEDIA_URL,
            params={
                "action": "query",
                "list": "search",
                "srnamespace": 6,
                "srsearch": query,
                "format": "json",
            },
        )
        if getattr(resp, "status_code", 200) != 200:
            return None
        hits = (resp.json() or {}).get("query", {}).get("search") or []
        if not hits:
            return None
        title = hits[0].get("title", "")
        info = self._get(
            WIKIMEDIA_URL,
            params={
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
            },
        )
        if getattr(info, "status_code", 200) != 200:
            return None
        pages = (info.json() or {}).get("query", {}).get("pages", {})
        for page in pages.values():
            ii = page.get("imageinfo") or []
            if ii:
                return ImageHit(
                    url=ii[0].get("url", ""),
                    source_url=ii[0].get("descriptionurl", ii[0].get("url", "")),
                    provider=self.name,
                    alt=title,
                )
        return None


def pick_image(
    providers: list[ImageProvider], query: str, lang: str, used_urls: set[str]
) -> Optional[ImageHit]:
    """Перебор провайдеров по порядку; дедуп по URL (ТЗ §6.11)."""
    for provider in providers:
        if not provider.is_available():
            continue
        hit = provider.search(query, lang)
        if hit and hit.url and hit.url not in used_urls:
            used_urls.add(hit.url)
            return hit
    return None
