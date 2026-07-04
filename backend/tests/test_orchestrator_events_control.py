"""T-7: EventEmitter (event_id, list, pub/sub) и PipelineControl (stop, review)."""

from __future__ import annotations

import json
import threading
import time

import fakeredis
import pytest

from app.orchestrator.control import PipelineControl
from app.orchestrator.events import EventEmitter, events_list_key
from app.orchestrator.exceptions import PipelineStopped, ReviewTimeout


def _redis():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_event_ids_monotonic_and_listed():
    r = _redis()
    em = EventEmitter(r, "a1")
    e1 = em.emit("step_started", {"n": 1})
    e2 = em.emit("step_finished", {"n": 1})
    e3 = em.log("hi")
    assert [e1["event_id"], e2["event_id"], e3["event_id"]] == [1, 2, 3]
    hist = em.history()
    assert [e["event_id"] for e in hist] == [1, 2, 3]
    # durable list содержит все события
    assert r.llen(events_list_key("a1")) == 3


def test_pubsub_broadcast():
    r = _redis()
    em = EventEmitter(r, "a1")
    ps = r.pubsub()
    ps.subscribe(em.channel)
    em.emit("log_entry", {"message": "x"})
    # первое сообщение — подтверждение подписки, затем наше
    got = None
    for _ in range(10):
        m = ps.get_message(timeout=0.1, ignore_subscribe_messages=True)
        if m and m.get("type") == "message":
            got = json.loads(m["data"])
            break
    assert got and got["type"] == "log_entry"


def test_stop_signal_roundtrip():
    r = _redis()
    ctl = PipelineControl(r, "a1")
    assert not ctl.is_stop_requested()
    ctl.request_stop()
    assert ctl.is_stop_requested()
    with pytest.raises(PipelineStopped):
        ctl.raise_if_stopped()
    ctl.clear()
    assert not ctl.is_stop_requested()


def test_wait_for_review_returns_payload():
    r = _redis()
    ctl = PipelineControl(r, "a1", poll_interval=0.05)
    result = {}

    def waiter():
        result["payload"] = ctl.wait_for_review(timeout_seconds=5)

    t = threading.Thread(target=waiter)
    t.start()
    # публикуем, пока подписчик не получит
    publisher = PipelineControl(r, "a1")
    for _ in range(40):
        if publisher.confirm_review({"outline": {"h1": "X"}}) > 0:
            break
        time.sleep(0.05)
    t.join(timeout=3)
    assert result["payload"] == {"outline": {"h1": "X"}}


def test_wait_for_review_timeout():
    r = _redis()
    ctl = PipelineControl(r, "a1", poll_interval=0.02)
    with pytest.raises(ReviewTimeout):
        ctl.wait_for_review(timeout_seconds=0.1)
