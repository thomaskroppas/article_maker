"""T-11: REST API — auth, settings (Fernet, БД→.env), pipeline, articles, каталог, кэш."""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL не задан"
)

AUTH = ("admin", "secret")


@pytest.fixture(scope="module")
def client():
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.config import get_settings
    from app.db.session import engine

    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"БД недоступна: {e}")

    s = get_settings()
    s.basic_auth_username = "admin"
    s.basic_auth_password = "secret"
    s.settings_encryption_key = Fernet.generate_key().decode()

    from app.main import app

    return TestClient(app)


# ─── auth ───
def test_health_no_auth(client):
    assert client.get("/api/health").status_code == 200


def test_settings_requires_auth(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings", auth=AUTH).status_code == 200


# ─── settings: Fernet + БД→.env, ключи не раскрываются ───
def test_settings_masks_keys_and_persists_encrypted(client):
    r = client.put("/api/settings", json={"serper_api_key": "SECRET123", "serp_provider": "serper"}, auth=AUTH)
    assert r.status_code == 204

    r = client.get("/api/settings", auth=AUTH)
    body = r.json()
    assert body["serper_key_set"] is True
    assert "SECRET123" not in r.text  # ключ не возвращается

    # в БД значение зашифровано (неплейнтекст), а get() расшифровывает
    from app.db.models import AppSetting
    from app.db.session import SessionLocal
    from app.settings_service import SettingsService

    with SessionLocal() as db:
        row = db.get(AppSetting, "serper_api_key")
        assert row is not None and "SECRET123" not in row.value  # шифртекст
        assert SettingsService(db).get("serper_api_key") == "SECRET123"  # применяется сразу


# ─── catalog ───
def test_niches_and_archetypes(client):
    assert len(client.get("/api/niches", auth=AUTH).json()) == 7
    arch = client.get("/api/archetypes", auth=AUTH, params={"niche_id": "travel"}).json()
    assert arch and all(a["niche_id"] == "travel" for a in arch)


# ─── pipeline run/status/events (redis + celery замоканы) ───
def test_pipeline_run_and_events(client, monkeypatch):
    import app.api.pipeline as pl

    enqueued = {}
    monkeypatch.setattr(pl, "get_redis", _fake_redis_factory())

    class _Task:
        def delay(self, aid):
            enqueued["id"] = aid

    monkeypatch.setattr("app.worker.run_pipeline", _Task())

    body = _article_input_json()
    r = client.post("/api/pipeline/run", json=body, auth=AUTH)
    assert r.status_code == 200
    aid = r.json()["article_id"]
    assert r.json()["ws_url"].endswith(aid)
    assert enqueued["id"] == aid

    # status
    st = client.get(f"/api/pipeline/{aid}/status", auth=AUTH)
    assert st.status_code == 200 and st.json()["status"] == "created"

    # events (из fakeredis — пусто, но структура корректна)
    ev = client.get(f"/api/pipeline/{aid}/events", auth=AUTH)
    assert ev.status_code == 200 and "events" in ev.json()

    client.delete(f"/api/articles/{aid}", auth=AUTH)  # cleanup


# ─── articles list/get/delete ───
def test_articles_crud_and_folder_delete(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.db.models import Article, Site
    from app.db.session import SessionLocal

    aid = uuid.uuid4()
    with SessionLocal() as db:
        if db.get(Site, "example.net") is None:
            db.add(Site(domain="example.net", name="Ex"))
            db.commit()
        db.add(Article(article_id=aid, site_domain="example.net", language="ru", status="completed"))
        db.commit()

    art_dir = tmp_path / "articles" / str(aid)
    art_dir.mkdir(parents=True)
    (art_dir / "final_package.json").write_text('{"article_markdown":"# T"}', encoding="utf-8")

    assert any(a["article_id"] == str(aid) for a in client.get("/api/articles", auth=AUTH).json())
    assert client.get(f"/api/articles/{aid}", auth=AUTH).status_code == 200
    assert client.get(f"/api/articles/{aid}/result", auth=AUTH).json()["article_markdown"] == "# T"

    assert client.delete(f"/api/articles/{aid}", auth=AUTH).status_code == 204
    assert not art_dir.exists()  # папка удалена
    assert client.get(f"/api/articles/{aid}", auth=AUTH).status_code == 404


# ─── helpers ───
def _article_input_json():
    return {
        "article_title": "Тест API Байкал",
        "main_keyword": "байкал",
        "secondary_keywords": ["дно"],
        "language": "ru",
        "geo": "ru",
        "intent": "informational",
        "article_type": "informational",
        "difficulty": "easy",
        "style_archetype": "expert_clear",
        "required_elements": ["faq"],
        "review_outline": False,
    }


def _fake_redis_factory():
    import fakeredis

    shared = fakeredis.FakeStrictRedis(decode_responses=True)
    return lambda: shared
