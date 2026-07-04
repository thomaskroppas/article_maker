"""
serp_loader — загружает SERP-данные из JSON файла краулера.

Ожидаемый формат JSON:
{
  "query": "байкал где находится",
  "language": "ru",
  "geo": "Россия",
  "lsi_terms": ["байкал", "сибирь", "иркутск"],
  "pages": [
    {
      "url": "https://example.com",
      "title": "Заголовок страницы",
      "word_count": 1200,
      "headings": {
        "h1": ["Байкал"],
        "h2": ["Где находится", "Глубина"],
        "h3": ["Острова", "Климат"]
      }
    }
  ]
}

Поле "content" не используется — агент работает только по заголовкам и метрикам.
lsi_terms — опционально. Если не передаёшь — оставь пустым списком [].
"""
import csv
import io
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

from app.schemas.serp_bundle import SerpBundle, PageData, AggregatedData, HeadingsData
from app.services.serp_cache import get_cached, save_cache

logger = logging.getLogger(__name__)


def load_from_file(path: str) -> SerpBundle:
    fpath = Path(path)
    if not fpath.exists():
        raise FileNotFoundError(f"SERP JSON файл не найден: {path}")
    raw = json.loads(fpath.read_text(encoding="utf-8"))
    return _parse_raw(raw)


def load_from_cache(query: str, language: str, geo: str) -> Optional[SerpBundle]:
    cached = get_cached(query, language, geo)
    if cached:
        logger.info(f"SERP: загружен кеш для '{query}'")
        return SerpBundle(**cached)
    return None


def _parse_raw(raw: dict) -> SerpBundle:
    query    = raw.get("query", "")
    language = raw.get("language", "ru")
    geo      = raw.get("geo", "")

    pages = []
    for p in raw.get("pages", []):
        h = p.get("headings", {})
        headings = HeadingsData(
            h1=h.get("h1", []),
            h2=h.get("h2", []),
            h3=h.get("h3", []),
        )
        pages.append(PageData(
            url        = p.get("url", ""),
            title      = p.get("title", ""),
            word_count = p.get("word_count", 0),
            headings   = headings,
            content    = "",
        ))

    if not pages:
        raise ValueError("SERP JSON не содержит ни одной страницы")

    wc_list = [p.word_count for p in pages if p.word_count > 0]
    all_h2  = []
    for p in pages:
        all_h2.extend(p.headings.h2)

    h2_counter      = Counter(all_h2)
    common_headings = [h for h, cnt in h2_counter.most_common(20) if cnt >= 2]

    aggregated = AggregatedData(
        avg_word_count  = sum(wc_list) / len(wc_list) if wc_list else 0,
        min_word_count  = min(wc_list) if wc_list else 0,
        max_word_count  = max(wc_list) if wc_list else 0,
        common_headings = common_headings,
        lsi_terms       = raw.get("lsi_terms", []),
    )

    secondary_keywords = raw.get("secondary_keywords", [])

    manual_sources = raw.get("sources", [])

    bundle = SerpBundle(
        query        = query,
        language     = language,
        geo          = geo,
        urls         = [p.url for p in pages],
        pages        = pages,
        aggregated   = aggregated,
        analysis_csv = _build_csv(pages),
        contents_txt = _build_structure(pages),
    )

    # Прикрепляем ключи к объекту для передачи в форму

    # Сохраняем источники отдельно — они не часть SerpBundle, передаются в article_input
    bundle._manual_sources = manual_sources  # временный атрибут для передачи в orchestrator
    save_cache(query, language, geo, bundle.to_dict())
    return bundle


def _build_csv(pages: list) -> str:
    buf    = io.StringIO()
    fields = ["url", "title", "word_count", "h1_count", "h2_count", "h3_count"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for p in pages:
        writer.writerow({
            "url":        p.url,
            "title":      p.title,
            "word_count": p.word_count,
            "h1_count":   len(p.headings.h1),
            "h2_count":   len(p.headings.h2),
            "h3_count":   len(p.headings.h3),
        })
    return buf.getvalue()


def _build_structure(pages: list) -> str:
    parts = []
    for i, p in enumerate(pages, 1):
        lines = [
            "--- САЙТ " + str(i) + " ---",
            "URL: " + p.url,
            "Слов: " + str(p.word_count),
        ]
        if p.headings.h1:
            lines.append("H1: " + p.headings.h1[0])
        if p.headings.h2:
            lines.append("H2: " + " | ".join(p.headings.h2))
        if p.headings.h3:
            lines.append("H3: " + " | ".join(p.headings.h3[:8]))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
