"""Ретраи LLM-вызовов при 429/500 (ТЗ §7.1, §14.1: exponential backoff).

Задержки 2s, 4s, 8s, 16s. Уважает stop-флаг (ТЗ §5.4): если запрошена остановка,
ретраи прекращаются немедленно.
"""

from __future__ import annotations

import time
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
_RETRYABLE_NAMES = {
    "RateLimitError",
    "InternalServerError",
    "APIConnectionError",
    "APITimeoutError",
    "OverloadedError",
    "ServiceUnavailableError",
}


class LLMStopRequested(Exception):
    """Ретраи прерваны stop-флагом."""


def is_retryable(exc: BaseException) -> bool:
    code = getattr(exc, "status_code", None)
    if code in _RETRYABLE_STATUS:
        return True
    return type(exc).__name__ in _RETRYABLE_NAMES


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 4,
    base_delay: float = 2.0,
    stop_flag: Optional[Callable[[], bool]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Выполнить fn с ретраями при retryable-ошибках.

    retries — число ПОВТОРОВ после первой попытки (итого до retries+1 попыток).
    Задержки: base_delay * 2**i (2, 4, 8, 16 при base_delay=2).
    """
    attempt = 0
    while True:
        if stop_flag is not None and stop_flag():
            raise LLMStopRequested("остановка запрошена до вызова LLM")
        try:
            return fn()
        except LLMStopRequested:
            raise
        except Exception as exc:  # noqa: BLE001
            if attempt >= retries or not is_retryable(exc):
                raise
            delay = base_delay * (2**attempt)
            attempt += 1
            # прерываемое ожидание: проверяем stop-флаг во время бэкоффа
            waited = 0.0
            step = min(0.5, delay)
            while waited < delay:
                if stop_flag is not None and stop_flag():
                    raise LLMStopRequested("остановка запрошена во время backoff")
                sleep(step)
                waited += step
