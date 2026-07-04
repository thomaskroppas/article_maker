"""WebSocket-протокол пайплайна — ТЗ §11.3.

Контракт: при подключении клиент получает ПОЛНУЮ историю событий из durable-list
`pipeline:events:{id}` (восстановление после reload, §10.4), затем — живой поток
из pub/sub `pipeline:{id}`. Каждое событие несёт монотонный event_id — клиент
дедуплицирует пересечение истории (GET /events) и WS-потока по event_id.
Аутентификация — query `?token=` (base64 "user:pass").
"""

from __future__ import annotations

import asyncio
import base64
import secrets
from typing import Callable, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..orchestrator.events import channel_key, events_list_key

router = APIRouter()

# Фабрика async-redis (переопределяется в тестах на fakeredis).
_async_redis_factory: Optional[Callable] = None


def set_async_redis_factory(factory: Optional[Callable]) -> None:
    global _async_redis_factory
    _async_redis_factory = factory


def _get_async_redis():
    if _async_redis_factory is not None:
        return _async_redis_factory()
    import redis.asyncio as aioredis

    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


def _check_token(token: str) -> bool:
    try:
        user, pw = base64.b64decode(token).decode().split(":", 1)
    except Exception:  # noqa: BLE001
        return False
    cfg = get_settings()
    return secrets.compare_digest(user, cfg.basic_auth_username) and secrets.compare_digest(
        pw, cfg.basic_auth_password or ""
    )


@router.websocket("/ws/pipeline/{article_id}")
async def ws_pipeline(websocket: WebSocket, article_id: str, token: str = "") -> None:
    if not _check_token(token):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    redis = _get_async_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_key(article_id))

    # 1) полная история (восстановление, §10.4)
    for raw in await redis.lrange(events_list_key(article_id), 0, -1):
        await websocket.send_text(raw)

    async def _forward():
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                await websocket.send_text(msg["data"])
            else:
                await asyncio.sleep(0.02)

    async def _receive():
        # ping/pong (§11.3.3) + детект отключения
        while True:
            data = await websocket.receive_text()
            if data and '"ping"' in data:
                await websocket.send_json({"type": "pong"})

    forward_task = asyncio.create_task(_forward())
    receive_task = asyncio.create_task(_receive())
    try:
        await asyncio.wait({forward_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        receive_task.cancel()
        try:
            await pubsub.unsubscribe(channel_key(article_id))
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
