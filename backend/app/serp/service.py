"""SerpService — оркестрация шага 1 (ТЗ §6.3).

Порядок: ручные источники (serp_json_path/manual_sources) → кэш → активный
провайдер. Живые вызовы провайдеров в тестах запрещены — HTTP/скачивание
инъектируются.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..schemas import AggregatedData, ArticleInput, PageData, SerpBundle
from .cache import SerpCache
from .extract import download_and_extract
from .providers import SerpProvider, build_provider


@dataclass
class SerpConfig:
    serp_provider: str = "serper"
    serper_api_key: str = ""
    xmlstock_api_url: str = ""


def _build_aggregated(pages: list[PageData]) -> AggregatedData:
    wcs = [p.word_count for p in pages if p.word_count]
    h2_counter: Counter[str] = Counter()
    for p in pages:
        for h2 in p.headings.h2:
            h2_counter[h2] += 1
    common = [h for h, c in h2_counter.items() if c >= 2]
    return AggregatedData(
        avg_word_count=round(statistics.fmean(wcs), 2) if wcs else 0.0,
        min_word_count=min(wcs) if wcs else 0,
        max_word_count=max(wcs) if wcs else 0,
        common_headings=common,
        lsi_terms=[],
    )


def _build_csv(pages: list[PageData]) -> str:
    rows = ["url,title,word_count,h2_count"]
    for p in pages:
        title = p.title.replace(",", " ").replace("\n", " ")
        rows.append(f"{p.url},{title},{p.word_count},{len(p.headings.h2)}")
    return "\n".join(rows)


def _build_contents(pages: list[PageData]) -> str:
    return "\n\n".join(f"## {p.title}\n{p.content}" for p in pages)


def _bundle_from_pages(
    query: str, geo: str, language: str, pages: list[PageData]
) -> SerpBundle:
    return SerpBundle(
        query=query,
        geo=geo,
        language=language,
        urls=[p.url for p in pages],
        pages=pages,
        aggregated=_build_aggregated(pages),
        analysis_csv=_build_csv(pages),
        contents_txt=_build_contents(pages),
    )


class SerpService:
    def __init__(
        self,
        cache: Optional[SerpCache] = None,
        http_post: Optional[Callable] = None,
        http_get: Optional[Callable] = None,
        page_fetch: Optional[Callable[[str, str], PageData]] = None,
    ):
        self.cache = cache if cache is not None else SerpCache()
        self._http_post = http_post
        self._http_get = http_get
        # page_fetch(url, title_hint) -> PageData (инъекция для тестов)
        self._page_fetch = page_fetch or (
            lambda url, hint: download_and_extract(url, hint, http_get=http_get)
        )

    def get_serp(self, ai: ArticleInput, cfg: SerpConfig) -> SerpBundle:
        # 1. Готовый bundle из файла — без сети и кэша.
        if ai.serp_json_path:
            data = json.loads(Path(ai.serp_json_path).read_text(encoding="utf-8"))
            return SerpBundle.model_validate(data)

        provider = build_provider(
            serp_provider=cfg.serp_provider,
            serper_api_key=cfg.serper_api_key,
            xmlstock_api_url=cfg.xmlstock_api_url,
            serp_json_path=ai.serp_json_path,
            manual_sources=ai.manual_sources,
            http_post=self._http_post,
            http_get=self._http_get,
        )

        # 2. Manual sources — скачиваем указанные URL, кэш не используется.
        if provider.name == "manual":
            provider.require_available()
            raw = provider.fetch(ai.main_keyword, ai.geo, ai.language)
            pages = [self._page_fetch(item["url"], item["title"]) for item in raw]
            return _bundle_from_pages(ai.main_keyword, ai.geo, ai.language, pages)

        # 3. Сетевой провайдер: кэш → fetch → скачивание → кэш.
        if not ai.force_refresh_serp:
            cached = self.cache.get(
                ai.main_keyword, ai.geo, ai.language, provider.name
            )
            if cached is not None:
                return cached

        provider.require_available()  # понятная ошибка конфигурации до сети (§6.3)
        raw = provider.fetch(ai.main_keyword, ai.geo, ai.language)
        pages = [self._page_fetch(item["url"], item["title"]) for item in raw]
        bundle = _bundle_from_pages(ai.main_keyword, ai.geo, ai.language, pages)
        self.cache.set(ai.main_keyword, ai.geo, ai.language, provider.name, bundle)
        return bundle
