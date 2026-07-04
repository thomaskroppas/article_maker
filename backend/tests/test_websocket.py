"""T-12: WebSocket — история при подключении + живой поток, дедуп по event_id."""

from __future__ import annotations

import base64
import json

import fakeredis
import pytest


@pytest.fixture()
def ws_setup(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    s.basic_auth_username = "admin"
    s.basic_auth_password = "secret"

    server = fakeredis.FakeServer()
    sync = fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    from app.api import websocket as ws_module

    ws_module.set_async_redis_factory(
        lambda: fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    yield sync
    ws_module.set_async_redis_factory(None)


def _token():
    return base64.b64encode(b"admin:secret").decode()


def test_ws_rejects_bad_token(ws_setup):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/pipeline/a1?token=bad") as ws:
            ws.receive_text()


def test_ws_history_then_live_no_dupes(ws_setup):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.orchestrator.events import EventEmitter

    sync = ws_setup
    em = EventEmitter(sync, "a1")
    # события ДО подключения (mid-pipeline) — попадут в историю
    em.emit("step_started", {"step_number": 1})
    em.emit("step_finished", {"step_number": 1})

    client = TestClient(app)
    with client.websocket_connect(f"/ws/pipeline/a1?token={_token()}") as ws:
        h1 = json.loads(ws.receive_text())
        h2 = json.loads(ws.receive_text())
        assert [h1["event_id"], h2["event_id"]] == [1, 2]

        # живое событие после подключения
        em.emit("log_entry", {"message": "live"})
        live = json.loads(ws.receive_text())
        assert live["event_id"] == 3
        assert live["type"] == "log_entry"

    # GET /events + WS вместе дают полную историю без дублей по event_id
    get_events = em.history()
    ws_seen = {h1["event_id"], h2["event_id"], live["event_id"]}
    combined = {e["event_id"] for e in get_events} | ws_seen
    assert combined == {1, 2, 3}  # дедуп по event_id
    assert len(get_events) == 3


def test_ws_ping_pong(ws_setup):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    with client.websocket_connect(f"/ws/pipeline/a2?token={_token()}") as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json() == {"type": "pong"}
