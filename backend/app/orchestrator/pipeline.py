"""PipelineOrchestrator — статусы, события, шаги 1–5, пауза ревью (ТЗ §6.1, §6.8).

Шаги 6–13 добавляются в T-8+. Здесь реализована механика оркестрации, на которую
они лягут: последовательные шаги со статусами/событиями, пауза review_outline с
таймаутом и stop-сигнал.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from ..agents.brief import BriefAgent
from ..agents.competitor import CompetitorAnalysisAgent
from ..agents.content_gaps import filter_content_gaps
from ..agents.lsi import LSIAgent
from ..agents.outline import OutlineAgent
from ..constants import REVIEW_TIMEOUT_HOURS, TOTAL_STEPS
from ..db.enums import ArticleStatus
from ..llm.cost import CostTracker
from ..schemas import Outline
from .control import PipelineControl
from .events import EventEmitter, EventType
from .exceptions import PipelineStopped, ReviewTimeout
from .status import InMemoryStatusManager, StatusManager


class PipelineOrchestrator:
    def __init__(
        self,
        article_input,
        *,
        emitter: EventEmitter,
        control: PipelineControl,
        status: StatusManager,
        llm,
        serp_service,
        serp_config,
        agent_cache=None,
        cost_tracker: Optional[CostTracker] = None,
        review_timeout_seconds: Optional[float] = None,
    ):
        self.ai = article_input
        self.emitter = emitter
        self.control = control
        self.status = status
        self.llm = llm
        self.serp_service = serp_service
        self.serp_config = serp_config
        self.agent_cache = agent_cache
        self.cost = cost_tracker or CostTracker()
        self.review_timeout_seconds = (
            review_timeout_seconds
            if review_timeout_seconds is not None
            else REVIEW_TIMEOUT_HOURS * 3600
        )

    # --- один шаг: stop-check → step_started → работа → step_finished/status ---
    def _run_step(
        self,
        step_name: str,
        step_number: int,
        status_after: Optional[str],
        fn: Callable,
    ):
        self.control.raise_if_stopped()
        self.emitter.emit(
            EventType.STEP_STARTED,
            {"step_name": step_name, "step_number": step_number, "total_steps": TOTAL_STEPS},
        )
        t0 = time.monotonic()
        result = fn()
        duration = time.monotonic() - t0
        self.status.record_step(
            step_name,
            step_number,
            "done",
            duration_ms=int(duration * 1000),
            cost_usd=self.cost.article_cost,
        )
        self.emitter.emit(
            EventType.STEP_FINISHED,
            {"step_name": step_name, "duration_seconds": round(duration, 3), "success": True},
        )
        if status_after:
            self.status.set_status(status_after)
        self.emitter.cost_update(
            self.cost.article_cost, self.cost.session_cost, self.cost.last_call_cost
        )
        self.control.raise_if_stopped()  # проверка и в конце шага (§5.4)
        return result

    def run(self) -> dict:
        try:
            self.status.set_status(ArticleStatus.INPUT_VALIDATED.value)

            competitor = CompetitorAnalysisAgent(self.llm, self.agent_cache)
            lsi_agent = LSIAgent(self.llm, self.agent_cache)
            brief_agent = BriefAgent(self.llm, self.agent_cache)
            outline_agent = OutlineAgent(self.llm, self.agent_cache)

            serp = self._run_step(
                "serp_analysis",
                1,
                ArticleStatus.SERP_DONE.value,
                lambda: self.serp_service.get_serp(self.ai, self.serp_config),
            )
            report = self._run_step(
                "competitor_analysis",
                2,
                ArticleStatus.COMPETITOR_ANALYSIS_DONE.value,
                lambda: competitor.run(self.ai, serp),
            )
            for w in competitor.warnings:
                self.emitter.log(w, level="warning")

            lsi = self._run_step(
                "lsi_keywords", 3, None, lambda: lsi_agent.run(self.ai, report)
            )
            brief = self._run_step(
                "brief_generation",
                4,
                ArticleStatus.BRIEF_DONE.value,
                lambda: brief_agent.run(self.ai, report, lsi_keywords=lsi),
            )
            outline = self._run_step(
                "outline_generation",
                5,
                ArticleStatus.OUTLINE_DONE.value,
                lambda: outline_agent.run(self.ai, brief, report),
            )
            for w in outline_agent.warnings:
                self.emitter.log(w, level="warning")

            if self.ai.review_outline:
                outline = self._review_pause(report, outline)

            # Вход в шаг 6 (секции реализуются в T-8+).
            self.status.set_status(ArticleStatus.SECTIONS_IN_PROGRESS.value)
            self.emitter.log(
                "Оркестратор довёл пайплайн до конца реализованных шагов (1–5). "
                "Шаги 6–13 будут добавлены в T-8+."
            )
            return {
                "serp_bundle": serp,
                "competitor_report": report,
                "lsi_keywords": lsi,
                "brief": brief,
                "outline": outline,
            }

        except PipelineStopped:
            self.status.set_status(ArticleStatus.STOPPED_BY_USER.value)
            self.emitter.emit(EventType.ABORTED, {"reason": "stopped_by_user"})
            return {"aborted": "stopped_by_user"}
        except ReviewTimeout:
            self.status.set_status(ArticleStatus.REVIEW_TIMEOUT.value)
            self.emitter.emit(EventType.ABORTED, {"reason": "review_timeout"})
            return {"aborted": "review_timeout"}
        except Exception as exc:  # noqa: BLE001
            self.status.set_status(ArticleStatus.FAILED.value)
            self.emitter.emit(EventType.ERROR, {"message": str(exc)})
            raise

    def _review_pause(self, report, outline: Outline) -> Outline:
        # FR-18: точки роста фильтруются от уже присутствующих в outline (§6.8).
        filtered = filter_content_gaps(
            report.content_gaps, [s.title for s in outline.sections]
        )
        self.emitter.emit(
            EventType.REVIEW_READY,
            {
                "competitor_summary": {
                    "word_count_range": report.word_count_range.model_dump(),
                    "h2_count_range": report.h2_count_range.model_dump(),
                    "must_have_topics": report.must_have_topics,
                },
                "content_gaps_filtered": [g.model_dump() for g in filtered],
                "archetype_suggestion": {},  # archetype_picker — далее
                "outline": outline.model_dump(),
            },
        )
        payload = self.control.wait_for_review(self.review_timeout_seconds)
        edited = payload.get("outline") if isinstance(payload, dict) else None
        if edited:
            outline = Outline.model_validate(edited)
            self.emitter.log("Ревью подтверждено с изменённым outline, продолжаем")
        else:
            self.emitter.log("Ревью подтверждено без изменений, продолжаем")
        return outline


def run_pipeline_sync(
    article_input,
    *,
    redis_client,
    llm,
    serp_service,
    serp_config,
    status: Optional[StatusManager] = None,
    agent_cache=None,
    cost_tracker: Optional[CostTracker] = None,
    review_timeout_seconds: Optional[float] = None,
) -> dict:
    """Синхронный прогон пайплайна (для Celery-задачи и интеграционных тестов)."""
    article_id = article_input.article_id
    orch = PipelineOrchestrator(
        article_input,
        emitter=EventEmitter(redis_client, article_id),
        control=PipelineControl(redis_client, article_id),
        status=status or InMemoryStatusManager(),
        llm=llm,
        serp_service=serp_service,
        serp_config=serp_config,
        agent_cache=agent_cache,
        cost_tracker=cost_tracker,
        review_timeout_seconds=review_timeout_seconds,
    )
    return orch.run()
