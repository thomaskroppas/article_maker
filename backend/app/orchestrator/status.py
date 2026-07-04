"""Управление статусами статьи (ТЗ §12, Приложение C) и записью шагов (§6.2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Protocol

from ..db.enums import TERMINAL_STATUSES, ArticleStatus
from ..db.models import Article, PipelineStep


class StatusManager(Protocol):
    def set_status(self, status: str) -> None: ...

    def record_step(
        self,
        step_name: str,
        step_number: int,
        status: str,
        *,
        duration_ms: Optional[int] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None: ...


_TERMINAL_VALUES = {s.value for s in TERMINAL_STATUSES}


class InMemoryStatusManager:
    """Для юнит-тестов оркестратора без БД."""

    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.steps: list[dict] = []

    def set_status(self, status: str) -> None:
        self.statuses.append(status)

    def record_step(self, step_name, step_number, status, **kw) -> None:
        self.steps.append({"step_name": step_name, "step_number": step_number, "status": status, **kw})


class DBStatusManager:
    """Пишет статусы и шаги в БД (articles / pipeline_steps)."""

    def __init__(self, session_factory, article_id: str):
        self._session_factory = session_factory
        self.article_id = uuid.UUID(str(article_id))

    def set_status(self, status: str) -> None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as s:
            article = s.get(Article, self.article_id)
            if article is None:
                return
            article.status = status
            if article.started_at is None and status != ArticleStatus.CREATED.value:
                article.started_at = now
            if status in _TERMINAL_VALUES:
                article.finished_at = now
            s.commit()

    def record_step(
        self,
        step_name,
        step_number,
        status,
        *,
        duration_ms=None,
        tokens_in=None,
        tokens_out=None,
        cost_usd=None,
        error_message=None,
    ) -> None:
        with self._session_factory() as s:
            s.add(
                PipelineStep(
                    article_id=self.article_id,
                    step_name=step_name,
                    step_number=step_number,
                    status=status,
                    duration_ms=duration_ms,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    error_message=error_message,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            s.commit()
