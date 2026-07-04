"""T-5: SERP-кэш (ключ, roundtrip) и извлечение страницы через readability."""

from __future__ import annotations

from app.schemas import SerpBundle
from app.serp.cache import SerpCache
from app.serp.extract import extract_from_html


def test_cache_key_includes_provider():
    k1 = SerpCache.make_key("Байкал", "ru", "ru", "serper")
    k2 = SerpCache.make_key("Байкал", "ru", "ru", "xmlstock")
    assert k1 != k2
    # регистр main_keyword не влияет (нормализация lower)
    assert SerpCache.make_key("байкал", "ru", "ru", "serper") == k1


def test_cache_roundtrip(tmp_path):
    cache = SerpCache(tmp_path)
    bundle = SerpBundle(query="байкал", geo="ru", language="ru", urls=["http://a"])
    assert cache.get("байкал", "ru", "ru", "serper") is None
    cache.set("байкал", "ru", "ru", "serper", bundle)
    loaded = cache.get("байкал", "ru", "ru", "serper")
    assert loaded is not None
    assert loaded.query == "байкал"
    assert loaded.urls == ["http://a"]


def test_extract_from_html_word_count_and_headings():
    html = """
    <html><body>
      <h1>Заголовок</h1>
      <article>
        <h2>Раздел A</h2>
        <p>Одно два три четыре пять шесть семь восемь девять десять.</p>
        <h2>Раздел B</h2>
        <h3>Подраздел</h3>
        <p>Ещё немного текста для объёма содержимого статьи здесь.</p>
      </article>
    </body></html>
    """
    page = extract_from_html("http://example.com", html)
    assert page.url == "http://example.com"
    assert page.word_count > 5
    assert "Раздел A" in page.headings.h2
    assert "Раздел B" in page.headings.h2
    assert page.headings.h1 == ["Заголовок"]
