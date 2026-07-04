"""T-1: smoke-тесты каркаса backend."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_openapi_available():
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "SEO Pipeline API"


def test_worker_ping_stub():
    # Задача worker'а импортируется и вызывается синхронно (без брокера).
    from app.worker import ping

    assert ping.run() == "pong"
