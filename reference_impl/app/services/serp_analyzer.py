"""
serp_analyzer — получает SERP, скачивает страницы, считает метрики.
Адаптация скрипта seo-analyzer из n8n-воркфлоу.
Использует XMLStock API для получения поисковой выдачи.
"""
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable

import requests
from bs4 import BeautifulSoup
try:
    from readability import Document
except ImportError:
    from readability.readability import Document

from app.config.settings import XMLSTOCK_API_URL
from app.config.pipeline_settings import (
    SERP_MIN_PAGES, SERP_MAX_PAGES,
    SERP_MAX_CONTENT_WORDS, SERP_WORKERS,
)
from app.schemas.serp_bundle import SerpBundle, PageData, AggregatedData, HeadingsData
from app.utils.text_utils import truncate_text
from app.services.serp_cache import get_cached, save_cache

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 15


# ─── Шаг 1: Получение SERP ───────────────────────────────────────────────────

def fetch_serp_urls(query: str, language: str, geo: str,
                    competitor_urls: Optional[List[str]] = None) -> List[dict]:
    """
    Возвращает список {'url': ..., 'title': ..., 'snippet': ...}
    Если переданы competitor_urls — использует их напрямую (без API).
    """
    # Если переданы URL вручную — использовать их
    if competitor_urls:
        logger.info(f"SERP: используем {len(competitor_urls)} URL из article_input")
        return [{"url": u, "title": "", "snippet": ""} for u in competitor_urls[:SERP_MAX_PAGES]]

    # Запрос к XMLStock API
    logger.info(f"SERP: запрос к XMLStock API. query='{query}' lang={language} geo={geo}")
    try:
        resp = requests.get(
            XMLSTOCK_API_URL,
            params={"query": query, "geo": geo, "group_by": SERP_MAX_PAGES},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("results", data.get("organic", []))
        result = []
        for item in items[:SERP_MAX_PAGES]:
            url = item.get("url") or item.get("link", "")
            if url:
                result.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                })
        logger.info(f"SERP: получено {len(result)} URL")
        return result
    except Exception as e:
        logger.error(f"SERP API ошибка: {e}")
        raise


# ─── Шаг 2: Скачивание и анализ страницы ─────────────────────────────────────

def fetch_html(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Определяем кодировку
        encoding = resp.apparent_encoding or "utf-8"
        return resp.content.decode(encoding, errors="replace")
    except Exception as e:
        logger.warning(f"Ошибка загрузки {url}: {e}")
        return None


def extract_content(html: str) -> tuple[str, str]:
    """Возвращает (clean_text, clean_html) с помощью readability."""
    doc = Document(html)
    clean_html = doc.summary(html_partial=True)
    soup = BeautifulSoup(clean_html, "lxml")
    text = soup.get_text(separator=" ", strip=True)
    return text, clean_html


def extract_headings(html: str) -> HeadingsData:
    soup = BeautifulSoup(html, "lxml")
    return HeadingsData(
        h1=[h.get_text(strip=True) for h in soup.find_all("h1")],
        h2=[h.get_text(strip=True) for h in soup.find_all("h2")],
        h3=[h.get_text(strip=True) for h in soup.find_all("h3")],
    )


def analyze_page(item: dict) -> Optional[PageData]:
    url = item["url"]
    html = fetch_html(url)
    if not html:
        return None

    try:
        text, clean_html = extract_content(html)
    except Exception as e:
        logger.warning(f"Readability ошибка для {url}: {e}")
        return None

    # Обрезаем контент
    text = truncate_text(text, SERP_MAX_CONTENT_WORDS)
    word_count = len(text.split())

    if word_count < 100:
        logger.warning(f"Слишком мало текста на {url}: {word_count} слов")
        return None

    headings = extract_headings(clean_html)

    return PageData(
        url=url,
        title=item.get("title", ""),
        word_count=word_count,
        headings=headings,
        content=text,
    )


# ─── Шаг 3: TF-IDF анализ ────────────────────────────────────────────────────

def compute_lsi_terms(texts: List[str], language: str,
                      top_n: int = 30) -> List[str]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np

        # Стоп-слова
        stop_words = []
        try:
            from stopwordsiso import stopwords
            stop_words = list(stopwords(language))
        except Exception:
            pass

        vec = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words=stop_words if stop_words else None,
            max_features=500,
        )
        matrix = vec.fit_transform(texts)
        scores = np.asarray(matrix.mean(axis=0)).flatten()
        indices = scores.argsort()[::-1][:top_n]
        terms = [vec.get_feature_names_out()[i] for i in indices]
        return terms
    except ImportError:
        logger.warning("scikit-learn не установлен, LSI пропускается")
        return []


# ─── Шаг 4: Формирование CSV и contents.txt ──────────────────────────────────

def build_analysis_csv(pages: List[PageData]) -> str:
    """Формирует CSV-строку в формате как у оригинального seo-analyzer."""
    import csv
    import io as _io

    buf = _io.StringIO()
    fieldnames = ["url", "title", "word_count", "h1_count", "h2_count", "h3_count"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for p in pages:
        writer.writerow({
            "url":       p.url,
            "title":     p.title,
            "word_count": p.word_count,
            "h1_count":  len(p.headings.h1),
            "h2_count":  len(p.headings.h2),
            "h3_count":  len(p.headings.h3),
        })
    return buf.getvalue()


def build_contents_txt(pages: List[PageData]) -> str:
    """Формирует contents.txt с маркерами как у seo-analyzer."""
    parts = []
    for i, p in enumerate(pages, 1):
        parts.append(f"--- САЙТ {i} ---\nURL: {p.url}\n\n{p.content}\n")
    return "\n".join(parts)


# ─── Главная функция ─────────────────────────────────────────────────────────

def run_serp_analysis(
    query: str,
    language: str,
    geo: str,
    competitor_urls: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    force_refresh: bool = False,
) -> SerpBundle:
    """
    Полный цикл SERP-анализа.
    progress_callback(msg) — опциональный коллбэк для GUI.
    force_refresh=True — игнорировать кеш и скачать заново.
    """
    def progress(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Проверяем кеш (если не форс-обновление и нет ручных URL)
    if not force_refresh and not competitor_urls:
        cached = get_cached(query, language, geo)
        if cached:
            progress(f"SERP: используется кеш для '{query}'.")
            return SerpBundle(**cached)

    progress(f"SERP: получение URL для '{query}'...")
    serp_items = fetch_serp_urls(query, language, geo, competitor_urls)

    if not serp_items:
        raise ValueError("SERP API не вернул результатов")

    progress(f"SERP: скачивание {len(serp_items)} страниц...")
    pages: List[PageData] = []

    with ThreadPoolExecutor(max_workers=SERP_WORKERS) as pool:
        futures = {pool.submit(analyze_page, item): item for item in serp_items}
        for future in as_completed(futures):
            result = future.result()
            if result:
                pages.append(result)
                progress(f"SERP: обработана страница {result.url[:60]}")

    if len(pages) < SERP_MIN_PAGES:
        raise ValueError(
            f"Недостаточно страниц для анализа: {len(pages)} < {SERP_MIN_PAGES}. "
            "Проверьте URL конкурентов или подключение к интернету."
        )

    progress(f"SERP: анализ LSI-ключей ({len(pages)} страниц)...")
    texts = [p.content for p in pages]
    lsi_terms = compute_lsi_terms(texts, language)

    # Агрегированная статистика
    wc_list = [p.word_count for p in pages]
    all_h2 = []
    for p in pages:
        all_h2.extend(p.headings.h2)

    # Частые H2 (встречаются хотя бы на 2 страницах)
    from collections import Counter
    h2_counter = Counter(all_h2)
    common_headings = [h for h, cnt in h2_counter.most_common(20) if cnt >= 2]

    aggregated = AggregatedData(
        avg_word_count=sum(wc_list) / len(wc_list),
        min_word_count=min(wc_list),
        max_word_count=max(wc_list),
        common_headings=common_headings,
        lsi_terms=lsi_terms,
    )

    analysis_csv  = build_analysis_csv(pages)
    contents_txt  = build_contents_txt(pages)

    progress(f"SERP: анализ завершён. Страниц: {len(pages)}, LSI: {len(lsi_terms)}")

    bundle = SerpBundle(
        query=query,
        language=language,
        geo=geo,
        urls=[p.url for p in pages],
        pages=pages,
        aggregated=aggregated,
        analysis_csv=analysis_csv,
        contents_txt=contents_txt,
    )

    # Сохраняем кеш (только если не ручные URL)
    if not competitor_urls:
        save_cache(query, language, geo, bundle.to_dict())

    return bundle
