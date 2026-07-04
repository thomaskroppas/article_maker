"""События пайплайна (ТЗ §11.3).

Каждое событие получает монотонный event_id и уходит в ДВА места:
- Redis pub/sub канал `pipeline:{id}` — для активных WebSocket-подписчиков;
- Redis list `pipeline:events:{id}` — durable-история для GET /events и
  восстановления после reconnect.
Дедупликация на клиенте — по event_id.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class EventType:
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"
    LOG_ENTRY = "log_entry"
    PROMPT_CAPTURED = "prompt_captured"
    SECTION_UPDATE = "section_update"
    COST_UPDATE = "cost_update"
    REVIEW_READY = "review_ready"
    FINISHED = "finished"
    ERROR = "error"
    ABORTED = "aborted"


def channel_key(article_id: str) -> str:
    return f"pipeline:{article_id}"


def events_list_key(article_id: str) -> str:
    return f"pipeline:events:{article_id}"


def _seq_key(article_id: str) -> str:
    return f"pipeline:eventseq:{article_id}"


class EventEmitter:
    def __init__(self, redis_client, article_id: str):
        self.redis = redis_client
        self.article_id = article_id
        self.channel = channel_key(article_id)
        self.list_key = events_list_key(article_id)
        self._seq_key = _seq_key(article_id)

    def emit(self, event_type: str, data: dict | None = None) -> dict:
        event_id = int(self.redis.incr(self._seq_key))
        event = {
            "type": event_type,
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        payload = json.dumps(event, ensure_ascii=False)
        # durable-история + широковещание
        self.redis.rpush(self.list_key, payload)
        self.redis.publish(self.channel, payload)
        return event

    def history(self) -> list[dict]:
        raw = self.redis.lrange(self.list_key, 0, -1)
        out = []
        for item in raw:
            if isinstance(item, bytes):
                item = item.decode("utf-8")
            out.append(json.loads(item))
        return out

    # --- удобные обёртки ---
    def log(self, message: str, level: str = "info") -> dict:
        return self.emit(EventType.LOG_ENTRY, {"level": level, "message": message})

    def cost_update(self, article: float, session: float, last_call: float) -> dict:
        return self.emit(
            EventType.COST_UPDATE,
            {"article": article, "session": session, "last_call": last_call},
        )
