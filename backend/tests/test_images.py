"""T-8: картинки — ротация ключей, fallback провайдеров, дедуп, обработка, вставка."""

from __future__ import annotations

import io

import pytest

from app.images.finder import find_insertion_points, run_image_stage
from app.images.keys import ImageKeysAgent, ImageKeysCache
from app.images.processor import process_image
from app.images.providers import (
    ImageHit,
    PixabayProvider,
    UnsplashProvider,
    WikimediaProvider,
    pick_image,
)
from app.llm import MockLLMClient


class FakeResp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code

    def json(self):
        return self._p


# --- ротация ключей при 429 (ключевой пункт DoD) ---
def test_pixabay_rotates_key_on_429():
    calls = []
    hit_payload = {"hits": [{"largeImageURL": "http://img/1.jpg", "pageURL": "http://pix/1", "tags": "baikal"}]}

    def fake_get(url, *, headers=None, params=None, timeout=20):
        calls.append(params["key"])
        if params["key"] == "K1":
            return FakeResp({}, status_code=429)  # первый ключ исчерпан
        return FakeResp(hit_payload)

    p = PixabayProvider(["K1", "K2"], http_get=fake_get)
    hit = p.search("baikal", "ru")
    assert hit and hit.url == "http://img/1.jpg"
    assert calls == ["K1", "K2"]  # была ротация
    assert p.current_key == "K2"


def test_pixabay_all_keys_exhausted_returns_none():
    p = PixabayProvider(["K1", "K2"], http_get=lambda *a, **k: FakeResp({}, status_code=429))
    assert p.search("q", "ru") is None


def test_unsplash_rotates_on_429():
    def fake_get(url, *, headers=None, params=None, timeout=20):
        key = headers["Authorization"].split()[-1]
        if key == "U1":
            return FakeResp({}, status_code=429)
        return FakeResp({"results": [{"urls": {"regular": "http://u/1"}, "links": {"html": "http://un/1"}}]})

    p = UnsplashProvider(["U1", "U2"], http_get=fake_get)
    hit = p.search("q", "ru")
    assert hit.url == "http://u/1"
    assert p.current_key == "U2"


# --- fallback и дедуп ---
def test_pick_image_fallback_and_dedup():
    p1 = PixabayProvider(["K"], http_get=lambda *a, **k: FakeResp({"hits": []}))  # пусто
    p2 = UnsplashProvider(
        ["U"],
        http_get=lambda *a, **k: FakeResp(
            {"results": [{"urls": {"regular": "http://u/1"}, "links": {"html": "http://un/1"}}]}
        ),
    )
    used = set()
    hit = pick_image([p1, p2], "q", "ru", used)
    assert hit.provider == "unsplash"
    assert "http://u/1" in used
    # повторный вызов с тем же url в used → дедуп (провайдер вернёт тот же url)
    assert pick_image([p2], "q", "ru", used) is None


def test_unavailable_provider_skipped():
    empty = PixabayProvider([], http_get=lambda *a, **k: FakeResp({"hits": []}))
    assert not empty.is_available()
    assert pick_image([empty], "q", "ru", set()) is None


# --- image_keys_agent + кэш ---
def test_image_keys_agent_and_cache(tmp_path):
    resp = '["baikal lake", "siberia nature", "deep water"]'
    cache = ImageKeysCache(tmp_path / "keys.json")

    class _AI:
        article_title = "Байкал"
        main_keyword = "байкал"
        secondary_keywords = ["дно"]

    agent = ImageKeysAgent(MockLLMClient(responses={"image_keys_agent": resp}), cache)
    keys = agent.run(_AI())
    assert keys == ["baikal lake", "siberia nature", "deep water"]
    # второй раз — из кэша (LLM не нужен)
    agent2 = ImageKeysAgent(MockLLMClient(), cache)
    assert agent2.run(_AI()) == keys


# --- обработка (Pillow): resize/crop 16:9/webp ---
def test_process_image_webp_16x9():
    from PIL import Image

    raw = io.BytesIO()
    Image.new("RGB", (4000, 3000), (10, 20, 30)).save(raw, format="PNG")
    out = process_image(raw.getvalue())
    assert out[:4] == b"RIFF" and out[8:12] == b"WEBP"  # WebP-сигнатура
    img = Image.open(io.BytesIO(out))
    assert max(img.size) <= 1920
    ratio = img.size[0] / img.size[1]
    assert abs(ratio - 16 / 9) < 0.05


# --- finder: точки вставки и вставка ---
def test_find_insertion_points_skips_faq_and_short():
    md = (
        "# T\n\n## Большой раздел\n" + ("слово " * 80) + "\n\n"
        "## FAQ\nвопросы\n\n## Короткий\nмало\n\n<!-- IMAGE: схема -->\n"
    )
    pts = find_insertion_points(md)
    kinds = [k for k, _ in pts]
    assert "placeholder" in kinds  # плейсхолдер найден
    assert "heading" in kinds  # большой раздел
    # FAQ и короткий раздел не дают точку вставки
    lines = md.split("\n")
    head_idxs = [i for k, i in pts if k == "heading"]
    assert all("FAQ" not in lines[i] and "Короткий" not in lines[i] for i in head_idxs)


def test_run_image_stage_inserts_and_dedups(tmp_path):
    class _AI:
        language = "ru"
        main_keyword = "байкал"

    urls = iter(["http://a/1", "http://a/2", "http://a/1"])  # третий дубль

    class OneShot(PixabayProvider):
        def search(self, query, lang):
            try:
                u = next(urls)
            except StopIteration:
                return None
            return ImageHit(url=u, source_url=u + "/src", provider="pixabay", alt="x")

    provider = OneShot(["K"])
    md = "# T\n\n## Раздел 1\n" + ("слово " * 80) + "\n\n## Раздел 2\n" + ("слово " * 80)
    out = run_image_stage(
        md, _AI(), keys=["baikal"], providers=[provider],
        article_dir=tmp_path, downloader=lambda url: b"IMG", processor=lambda b: b"WEBP",
    )
    assert out.count("![") == 2  # две картинки вставлены
    assert (tmp_path / "images" / "0.webp").exists()
    assert (tmp_path / "images" / "1.webp").exists()
