"""SerpProvider — интерфейс шага 1 и три реализации (ТЗ §6.3, §14.2).

fetch(query, geo, hl) возвращает сырой топ-10 органической выдачи:
list[{url, title, description}]. Скачивание страниц и readability — выше по
потоку (service.py). HTTP-вызовы инъектируются, чтобы в тестах не ходить в сеть
(живые вызовы SERP-провайдеров запрещены).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

SERPER_ENDPOINT = "https://google.serper.dev/search"


class SerpProviderError(RuntimeError):
    """Провайдер недоступен или вернул некорректный ответ."""


class SerpProvider(ABC):
    name: str = ""

    def is_available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return f"SERP-провайдер {self.name} недоступен"

    def require_available(self) -> None:
        if not self.is_available():
            raise SerpProviderError(self.unavailable_reason)

    @abstractmethod
    def fetch(self, query: str, geo: str, hl: str) -> list[dict]: ...


def _default_post(url, *, headers=None, json=None, timeout=20):
    import requests

    return requests.post(url, headers=headers, json=json, timeout=timeout)


def _default_get(url, *, params=None, timeout=20):
    import requests

    return requests.get(url, params=params, timeout=timeout)


class SerperDevProvider(SerpProvider):
    """Основной провайдер — serper.dev (POST, X-API-KEY, organic top-10)."""

    name = "serper"

    def __init__(self, api_key: str, http_post: Optional[Callable] = None):
        self.api_key = (api_key or "").strip()
        self._post = http_post or _default_post

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def unavailable_reason(self) -> str:
        return "SERP-провайдер serper недоступен: не задан serper_api_key"

    def fetch(self, query: str, geo: str, hl: str) -> list[dict]:
        self.require_available()
        resp = self._post(
            SERPER_ENDPOINT,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "gl": geo, "hl": hl},
            timeout=20,
        )
        if getattr(resp, "status_code", 200) != 200:
            raise SerpProviderError(f"serper.dev вернул HTTP {resp.status_code}")
        data = resp.json()
        organic = data.get("organic") or []
        out = []
        for item in organic[:10]:
            out.append(
                {
                    "url": item.get("link") or item.get("url") or "",
                    "title": item.get("title", ""),
                    "description": item.get("snippet", ""),
                }
            )
        return [o for o in out if o["url"]]


class XmlstockProvider(SerpProvider):
    """Альтернатива — любой xmlstock-совместимый эндпоинт (GET)."""

    name = "xmlstock"

    def __init__(self, api_url: str, http_get: Optional[Callable] = None):
        self.api_url = (api_url or "").strip()
        self._get = http_get or _default_get

    def is_available(self) -> bool:
        return bool(self.api_url)

    @property
    def unavailable_reason(self) -> str:
        return "SERP-провайдер xmlstock недоступен: не задан XMLSTOCK_API_URL"

    def fetch(self, query: str, geo: str, hl: str) -> list[dict]:
        self.require_available()
        resp = self._get(
            self.api_url, params={"q": query, "geo": geo, "hl": hl}, timeout=20
        )
        if getattr(resp, "status_code", 200) != 200:
            raise SerpProviderError(f"xmlstock вернул HTTP {resp.status_code}")
        data = resp.json()
        items = data.get("items") if isinstance(data, dict) else data
        items = items or []
        out = []
        for item in items[:10]:
            out.append(
                {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                }
            )
        return [o for o in out if o["url"]]


class ManualProvider(SerpProvider):
    """Ручные источники: serp_json_path (готовый bundle) или manual_sources (список URL).

    serp_json_path обрабатывается сервисом напрямую (загрузка bundle), поэтому
    fetch() отдаёт URL из manual_sources как «сырую выдачу» без title/description.
    """

    name = "manual"

    def __init__(
        self,
        serp_json_path: Optional[str] = None,
        manual_sources: Optional[list[str]] = None,
    ):
        self.serp_json_path = serp_json_path
        self.manual_sources = manual_sources or []

    def is_available(self) -> bool:
        return bool(self.serp_json_path or self.manual_sources)

    @property
    def unavailable_reason(self) -> str:
        return "SERP-провайдер manual недоступен: не заданы serp_json_path/manual_sources"

    def fetch(self, query: str, geo: str, hl: str) -> list[dict]:
        self.require_available()
        return [{"url": u, "title": "", "description": ""} for u in self.manual_sources]


def build_provider(
    *,
    serp_provider: str,
    serper_api_key: str = "",
    xmlstock_api_url: str = "",
    serp_json_path: Optional[str] = None,
    manual_sources: Optional[list[str]] = None,
    http_post: Optional[Callable] = None,
    http_get: Optional[Callable] = None,
) -> SerpProvider:
    """Выбор провайдера (ТЗ §6.3): ручные источники → manual; иначе по serp_provider."""
    if serp_json_path or manual_sources:
        return ManualProvider(serp_json_path=serp_json_path, manual_sources=manual_sources)
    if serp_provider == "xmlstock":
        return XmlstockProvider(xmlstock_api_url, http_get=http_get)
    return SerperDevProvider(serper_api_key, http_post=http_post)
