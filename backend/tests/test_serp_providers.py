"""T-5: три провайдера на моках + выбор провайдера + is_available (§6.3, §14.2).

Живые вызовы SERP-провайдеров запрещены — HTTP инъектируется фейками.
"""

from __future__ import annotations

import pytest

from app.serp.providers import (
    ManualProvider,
    SerpProviderError,
    SerperDevProvider,
    XmlstockProvider,
    build_provider,
)


class FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


# --- serper.dev ---
def test_serper_parses_organic_top10():
    payload = {"organic": [{"link": f"http://u{i}", "title": f"t{i}", "snippet": f"s{i}"} for i in range(15)]}
    captured = {}

    def fake_post(url, *, headers=None, json=None, timeout=20):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResp(payload)

    p = SerperDevProvider("KEY", http_post=fake_post)
    out = p.fetch("байкал", "ru", "ru")
    assert captured["url"] == "https://google.serper.dev/search"
    assert captured["headers"]["X-API-KEY"] == "KEY"
    assert captured["json"] == {"q": "байкал", "gl": "ru", "hl": "ru"}
    assert len(out) == 10
    assert out[0] == {"url": "http://u0", "title": "t0", "description": "s0"}


def test_serper_unavailable_without_key():
    p = SerperDevProvider("")
    assert not p.is_available()
    assert "serper_api_key" in p.unavailable_reason
    with pytest.raises(SerpProviderError):
        p.fetch("q", "ru", "ru")


def test_serper_raises_on_http_error():
    p = SerperDevProvider("KEY", http_post=lambda *a, **k: FakeResp({}, status_code=500))
    with pytest.raises(SerpProviderError):
        p.fetch("q", "ru", "ru")


# --- xmlstock ---
def test_xmlstock_parses_items():
    payload = {"items": [{"url": f"http://x{i}", "title": f"t{i}", "description": f"d{i}"} for i in range(12)]}
    p = XmlstockProvider("http://host/serp", http_get=lambda *a, **k: FakeResp(payload))
    out = p.fetch("q", "ru", "ru")
    assert len(out) == 10
    assert out[0]["url"] == "http://x0"


def test_xmlstock_unavailable_without_url():
    p = XmlstockProvider("")
    assert not p.is_available()
    assert "XMLSTOCK_API_URL" in p.unavailable_reason
    with pytest.raises(SerpProviderError):
        p.fetch("q", "ru", "ru")


# --- manual ---
def test_manual_from_sources():
    p = ManualProvider(manual_sources=["http://a", "http://b"])
    assert p.is_available()
    out = p.fetch("q", "ru", "ru")
    assert [o["url"] for o in out] == ["http://a", "http://b"]


def test_manual_unavailable_when_empty():
    assert not ManualProvider().is_available()


# --- выбор провайдера ---
def test_build_provider_manual_when_json_path():
    p = build_provider(serp_provider="serper", serper_api_key="k", serp_json_path="/x.json")
    assert p.name == "manual"


def test_build_provider_manual_when_sources():
    p = build_provider(serp_provider="serper", serper_api_key="k", manual_sources=["http://a"])
    assert p.name == "manual"


def test_build_provider_serper_default():
    assert build_provider(serp_provider="serper", serper_api_key="k").name == "serper"


def test_build_provider_xmlstock_selected():
    p = build_provider(serp_provider="xmlstock", xmlstock_api_url="http://h")
    assert p.name == "xmlstock"
