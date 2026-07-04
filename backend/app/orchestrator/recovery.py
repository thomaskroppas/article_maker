"""Восстановление осиротевших прогонов (доделка T-7).

Если воркер перезапущен/упал, его Celery-задачи гибнут, а статьи остаются в
нетерминальных статусах (напр. outline_done на паузе ревью) навсегда: слушать
stop/resume некому, а по статусу они выглядят «активными». Здесь — перевод таких
статей в failed с понятной причиной.

Защита от ложных срабатываний: статьи, чьи article_id присутствуют в активных/
зарезервированных Celery-задачах, не трогаются. Ограничение: надёжно для
single-worker dev-развёртывания; для multi-worker см. заметку в QUESTIONS.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..db.enums import TERMINAL_STATUSES, ArticleStatus
from ..db.models import Article, PipelineStep
from .events import EventEmitter, EventType

_TERMINAL = {s.value for s in TERMINAL_STATUSES}
DEFAULT_REASON = "worker restarted"


def get_active_article_ids(celery_app, timeout: float = 2.0) -> set[str] | None:
    """article_id из активных/зарезервированных/запланированных задач run_pipeline.

    Возвращает None, если брокер недоступен (инспекция не удалась) — вызывающая
    сторона решает, как трактовать (на старте воркера — как «нет активных»).
    """
    try:
        insp = celery_app.control.inspect(timeout=timeout)
        buckets = [insp.active() or {}, insp.reserved() or {}, insp.scheduled() or {}]
    except Exception:  # noqa: BLE001
        return None
    ids: set[str] = set()
    for data in buckets:
        for _worker, tasks in (data or {}).items():
            for t in tasks or []:
                req = t.get("request", t)  # scheduled оборачивает в 'request'
                name = req.get("name", "") or ""
                args = req.get("args") or []
                if name.endswith("run_pipeline") and args:
                    ids.add(str(args[0]))
    return ids


def recover_orphaned_pipelines(
    session_factory,
    active_ids: set[str],
    *,
    redis_client=None,
    reason: str = DEFAULT_REASON,
) -> list[str]:
    """Перевести нетерминальные статьи (не в active_ids) в failed. Вернуть их id."""
    now = datetime.now(timezone.utc)
    recovered: list[str] = []
    with session_factory() as s:
        rows = s.query(Article).filter(Article.status.notin_(_TERMINAL)).all()
        for article in rows:
            if str(article.article_id) in active_ids:
                continue
            article.status = ArticleStatus.FAILED.value
            article.finished_at = now
            s.add(
                PipelineStep(
                    article_id=article.article_id,
                    step_name="orphan_recovery",
                    status="failed",
                    error_message=reason,
                    finished_at=now,
                )
            )
            recovered.append(str(article.article_id))
        s.commit()

    if redis_client is not None:
        for aid in recovered:
            EventEmitter(redis_client, aid).emit(
                EventType.ABORTED, {"reason": reason}
            )
    return recovered
