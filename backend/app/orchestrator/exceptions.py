"""Исключения управления пайплайном."""

from __future__ import annotations


class PipelineStopped(Exception):
    """Пользователь/система запросили остановку (§5.4)."""


class ReviewTimeout(Exception):
    """Ревью outline не подтверждено за REVIEW_TIMEOUT_HOURS (§6.8.1)."""
