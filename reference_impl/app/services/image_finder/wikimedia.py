"""
Провайдер картинок Wikimedia Commons.
REST API без ключа: ищем по теме, берём первое изображение.
Хорош для фактических объектов: озёра, горы, города, известные места.
"""
import logging
from typing import Optional
import urllib.parse
import requests

from app.services.image_finder.base import ImageProvider, ImageResult

logger = logging.getLogger(__name__)

_API_URL = "https://commons.wikimedia.org/w/api.php"

# Wikimedia требует осмысленный User-Agent в запросах от ботов/приложений.
# Без этого возвращает 403. Контакт можно поменять на свой email.
_HEADERS = {
    "User-Agent": "SEO-Pipeline/1.0 (https://github.com/thomaskroppas/ai_articles_pipeline)"
}


class WikimediaProvider(ImageProvider):
    name = "wikimedia"

    def search_many(self, query: str, language: str = "ru",
                    limit: int = 5) -> list[ImageResult]:
        try:
            params = {
                "action":   "query",
                "format":   "json",
                "list":     "search",
                "srnamespace": "6",
                "srsearch": query,
                "srlimit":  str(limit),
                "uselang":  language,
            }
            resp = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
            hits = resp.json().get("query", {}).get("search", [])
            if not hits:
                return []

            results: list[ImageResult] = []
            for hit in hits:
                file_title = hit["title"]
                params2 = {
                    "action":     "query",
                    "format":     "json",
                    "titles":     file_title,
                    "prop":       "imageinfo",
                    "iiprop":     "url|user",
                    "iiurlwidth": "1200",
                }
                r2 = requests.get(_API_URL, params=params2, headers=_HEADERS, timeout=10)
                if not r2.ok:
                    continue
                for _, page in r2.json().get("query", {}).get("pages", {}).items():
                    info = page.get("imageinfo", [{}])[0]
                    url = info.get("thumburl") or info.get("url")
                    if not url:
                        continue
                    source_url = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(file_title)
                    user = info.get("user") or "Wikimedia Commons"
                    results.append(ImageResult(
                        url=url,
                        source_url=source_url,
                        attribution=f"{user} / Wikimedia Commons",
                    ))
            return results
        except Exception as e:
            logger.warning(f"[wikimedia] поиск '{query}' упал: {e}")
            return []
