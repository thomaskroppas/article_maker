"""T-5: SerpService end-to-end на моках (§6.3).

Покрывает: загрузку готового bundle через serp_json_path (на fixture),
сетевой провайдер с кэшированием, попадание в кэш, ошибку конфигурации,
manual_sources. Живой SERP не вызывается.
"""

from __future__ import annotations

import os

import pytest

from app.paths import fixtures_dir
from app.schemas import ArticleInput, HeadingsData, PageData
from app.serp.providers import SerpProviderError
from app.serp.cache import SerpCache
from app.serp.service import SerpConfig, SerpService


def _ai(**over):
    base = dict(
        article_title="Где находится Байкал",
        main_keyword="байкал где находится",
        secondary_keywords=["байкал дно"],
        language="ru",
        geo="ru",
        intent="informational",
        article_type="informational",
        difficulty="easy",
        style_archetype="expert_clear",
        required_elements=["faq"],
    )
    base.update(over)
    return ArticleInput.model_validate(base)


def _fake_page(url, hint):
    return PageData(
        url=url,
        title=hint or "T",
        word_count=100,
        headings=HeadingsData(h2=["A", "B"]),
        content="слово " * 100,
    )


def test_serp_json_path_loads_fixture():
    fx = str(fixtures_dir() / "serp_bundle_example.json")
    svc = SerpService(page_fetch=_fake_page)
    bundle = svc.get_serp(_ai(serp_json_path=fx), SerpConfig())
    assert bundle.query
    assert len(bundle.pages) >= 1


def test_serper_path_builds_and_caches(tmp_path):
    calls = {"post": 0}

    def fake_post(url, *, headers=None, json=None, timeout=20):
        calls["post"] += 1

        class R:
            status_code = 200

            def json(self):
                return {"organic": [{"link": "http://a", "title": "A", "snippet": "s"},
                                     {"link": "http://b", "title": "B", "snippet": "s"}]}

        return R()

    svc = SerpService(cache=SerpCache(tmp_path), http_post=fake_post, page_fetch=_fake_page)
    cfg = SerpConfig(serp_provider="serper", serper_api_key="KEY")
    ai = _ai()

    bundle = svc.get_serp(ai, cfg)
    assert len(bundle.pages) == 2
    assert bundle.aggregated.avg_word_count == 100.0
    assert "A" in bundle.aggregated.common_headings  # H2 у обеих страниц
    assert calls["post"] == 1

    # второй вызов — попадание в кэш, сеть не дёргается
    bundle2 = svc.get_serp(ai, cfg)
    assert bundle2.urls == bundle.urls
    assert calls["post"] == 1


def test_force_refresh_bypasses_cache(tmp_path):
    calls = {"post": 0}

    def fake_post(url, *, headers=None, json=None, timeout=20):
        calls["post"] += 1

        class R:
            status_code = 200

            def json(self):
                return {"organic": [{"link": "http://a", "title": "A", "snippet": "s"}]}

        return R()

    svc = SerpService(cache=SerpCache(tmp_path), http_post=fake_post, page_fetch=_fake_page)
    cfg = SerpConfig(serp_provider="serper", serper_api_key="KEY")
    svc.get_serp(_ai(), cfg)
    svc.get_serp(_ai(force_refresh_serp=True), cfg)
    assert calls["post"] == 2


def test_config_error_before_network(tmp_path):
    svc = SerpService(cache=SerpCache(tmp_path), page_fetch=_fake_page)
    cfg = SerpConfig(serp_provider="serper", serper_api_key="")  # ключ не задан
    with pytest.raises(SerpProviderError) as exc:
        svc.get_serp(_ai(), cfg)
    assert "serper_api_key" in str(exc.value)


def test_manual_sources_downloads_pages():
    svc = SerpService(page_fetch=_fake_page)
    bundle = svc.get_serp(
        _ai(manual_sources=["http://x", "http://y"]), SerpConfig()
    )
    assert [p.url for p in bundle.pages] == ["http://x", "http://y"]
