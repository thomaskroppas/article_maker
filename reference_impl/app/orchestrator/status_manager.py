"""
Централизованное управление статусами статьи и шагов.
Уведомляет GUI через callback.
"""
import logging
from typing import Callable, Optional
from app.storage.repositories import update_article_status
from app.config.pipeline_settings import (
    STATUS_FAILED, STATUS_STOPPED,
    FINAL_STATUS_READY, FINAL_STATUS_READY_WARN, FINAL_STATUS_FAILED,
)

logger = logging.getLogger(__name__)


class StatusManager:
    def __init__(self, article_id: str,
                 on_status_change: Optional[Callable[[str, str], None]] = None):
        """
        on_status_change(step_name, status) — коллбэк для GUI.
        """
        self.article_id = article_id
        self._on_change = on_status_change
        self._current_status = "created"
        self._step_statuses: dict[str, str] = {}

    def set_article_status(self, status: str) -> None:
        self._current_status = status
        update_article_status(self.article_id, status)
        logger.info(f"[{self.article_id}] Статус статьи: {status}")
        if self._on_change:
            self._on_change("article", status)

    def set_step_status(self, step_name: str, status: str) -> None:
        """status: running | done | error | skipped"""
        self._step_statuses[step_name] = status
        logger.info(f"[{self.article_id}] Шаг '{step_name}': {status}")
        if self._on_change:
            self._on_change(step_name, status)

    def get_step_status(self, step_name: str) -> str:
        return self._step_statuses.get(step_name, "pending")

    def get_final_article_status(self, qa_status: str) -> str:
        if qa_status == "pass":
            return FINAL_STATUS_READY
        elif qa_status == "pass_with_warnings":
            return FINAL_STATUS_READY_WARN
        else:
            return FINAL_STATUS_FAILED

    @property
    def current_status(self) -> str:
        return self._current_status
