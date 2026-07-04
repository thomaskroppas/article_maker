"""T-4: ретраи 429/500 с exponential backoff и уважением stop-флага."""

from __future__ import annotations

import pytest

from app.llm.retry import LLMStopRequested, is_retryable, with_retry


class FakeStatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class RateLimitError(Exception):
    """Имя как у anthropic.RateLimitError — распознаётся по типу."""


def test_is_retryable_by_status():
    assert is_retryable(FakeStatusError(429))
    assert is_retryable(FakeStatusError(500))
    assert not is_retryable(FakeStatusError(400))


def test_is_retryable_by_name():
    assert is_retryable(RateLimitError())
    assert not is_retryable(ValueError("nope"))


def test_retries_then_succeeds():
    calls = {"n": 0}
    delays = []

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeStatusError(429)
        return "ok"

    result = with_retry(fn, base_delay=2.0, sleep=lambda s: delays.append(s))
    assert result == "ok"
    assert calls["n"] == 3
    # два бэкоффа: ~2s и ~4s (прерываемое ожидание шагами по 0.5)
    assert round(sum(delays), 1) == 6.0


def test_gives_up_after_retries():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise FakeStatusError(500)

    with pytest.raises(FakeStatusError):
        with_retry(fn, retries=2, base_delay=0.01, sleep=lambda s: None)
    assert calls["n"] == 3  # 1 + 2 повтора


def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("fatal")

    with pytest.raises(ValueError):
        with_retry(fn, sleep=lambda s: None)
    assert calls["n"] == 1


def test_stop_flag_aborts_before_call():
    def fn():
        raise AssertionError("не должно вызываться при остановке")

    with pytest.raises(LLMStopRequested):
        with_retry(fn, stop_flag=lambda: True, sleep=lambda s: None)


def test_stop_flag_aborts_during_backoff():
    calls = {"n": 0}
    flag = {"stop": False}

    def fn():
        calls["n"] += 1
        flag["stop"] = True  # после первой ошибки просим остановку
        raise FakeStatusError(429)

    with pytest.raises(LLMStopRequested):
        with_retry(
            fn, base_delay=2.0, stop_flag=lambda: flag["stop"], sleep=lambda s: None
        )
    assert calls["n"] == 1
