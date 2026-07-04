"""Общий доступ к Redis для API-роутеров."""

from __future__ import annotations

from ..config import get_settings


def get_redis():
    import redis as redis_lib

    return redis_lib.Redis.from_url(get_settings().redis_url, decode_responses=True)
