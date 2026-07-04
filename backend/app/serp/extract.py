"""Скачивание страниц и извлечение контента через readability-lxml (ТЗ §6.3)."""

from __future__ import annotations

from typing import Callable, Optional

from ..schemas import HeadingsData, PageData


def _headings(html: str) -> HeadingsData:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    def texts(tag: str) -> list[str]:
        return [e.get_text(" ", strip=True) for e in soup.find_all(tag)]

    return HeadingsData(h1=texts("h1"), h2=texts("h2"), h3=texts("h3"))


def extract_from_html(url: str, html: str, title_hint: str = "") -> PageData:
    from bs4 import BeautifulSoup
    from readability import Document

    headings = _headings(html)
    try:
        doc = Document(html)
        content_html = doc.summary()
        title = doc.short_title() or title_hint
    except Exception:  # noqa: BLE001 — при сбое readability берём как есть
        content_html = html
        title = title_hint
    text = BeautifulSoup(content_html, "lxml").get_text(" ", strip=True)
    return PageData(
        url=url,
        title=title,
        word_count=len(text.split()),
        headings=headings,
        content=text,
    )


def _default_get(url, *, timeout=20):
    import requests

    return requests.get(url, timeout=timeout)


def download_and_extract(
    url: str, title_hint: str = "", http_get: Optional[Callable] = None
) -> PageData:
    get = http_get or _default_get
    resp = get(url, timeout=20)
    html = getattr(resp, "text", "") or ""
    return extract_from_html(url, html, title_hint=title_hint)
