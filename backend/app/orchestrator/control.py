"""Управляющие сигналы: stop и пауза-ревью (ТЗ §5.4, §6.8, §6.8.1)."""

from __future__ import annotations

import json
import time
from typing import Optional

from .exceptions import PipelineStopped, ReviewTimeout


def control_key(article_id: str) -> str:
    return f"pipeline:control:{article_id}"


def review_channel(article_id: str) -> str:
    return f"review_confirmed:{article_id}"


class PipelineControl:
    def __init__(self, redis_client, article_id: str, poll_interval: float = 1.0):
        self.redis = redis_client
        self.article_id = article_id
        self.poll_interval = poll_interval
        self._control_key = control_key(article_id)
        self._review_channel = review_channel(article_id)

    # --- stop (durable key; воркер проверяет в конце каждого шага, §5.4) ---
    def request_stop(self) -> None:
        self.redis.set(self._control_key, json.dumps({"action": "stop"}))

    def is_stop_requested(self) -> bool:
        raw = self.redis.get(self._control_key)
        if not raw:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw).get("action") == "stop"
        except (ValueError, AttributeError):
            return False

    def raise_if_stopped(self) -> None:
        if self.is_stop_requested():
            raise PipelineStopped()

    def clear(self) -> None:
        self.redis.delete(self._control_key)

    # --- resume (публикация подтверждения ревью) ---
    def confirm_review(self, payload: dict) -> int:
        return int(self.redis.publish(self._review_channel, json.dumps(payload)))

    # --- ожидание подтверждения ревью с таймаутом (§6.8.1) ---
    def wait_for_review(self, timeout_seconds: float) -> dict:
        pubsub = self.redis.pubsub()
        pubsub.subscribe(self._review_channel)
        try:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                self.raise_if_stopped()
                msg = pubsub.get_message(
                    timeout=self.poll_interval, ignore_subscribe_messages=True
                )
                if msg and msg.get("type") == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    return json.loads(data)
            raise ReviewTimeout()
        finally:
            try:
                pubsub.close()
            except Exception:  # noqa: BLE001
                pass
