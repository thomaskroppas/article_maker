"""T-7: интеграция оркестратора — запуск/пауза/resume/timeout/stop (fakeredis)."""

from __future__ import annotations

import threading
import time

import fakeredis

from app.llm import CostTracker, MockLLMClient
from app.orchestrator.control import PipelineControl
from app.orchestrator.events import EventEmitter
from app.orchestrator.pipeline import PipelineOrchestrator
from app.orchestrator.status import InMemoryStatusManager
from app.db.enums import ArticleStatus
from app.paths import fixtures_dir
from app.schemas import ArticleInput
from app.serp.service import SerpConfig, SerpService


def _ai(**over):
    base = dict(
        article_title="Где находится Байкал",
        main_keyword="байкал где находится",
        secondary_keywords=["байкал дно"],
        language="ru",
        geo="ru",
        intent="informational",
        article_type="informational",
        difficulty="easy",
        style_archetype="expert_clear",
        required_elements=["faq"],
        serp_json_path=str(fixtures_dir() / "serp_bundle_example.json"),
    )
    base.update(over)
    return ArticleInput.model_validate(base)


def _make_orch(ai, r, status, *, review_timeout=5.0, cost=None):
    return PipelineOrchestrator(
        ai,
        emitter=EventEmitter(r, ai.article_id),
        control=PipelineControl(r, ai.article_id, poll_interval=0.05),
        status=status,
        llm=MockLLMClient(cost_tracker=cost),
        serp_service=SerpService(),
        serp_config=SerpConfig(),
        cost_tracker=cost,
        review_timeout_seconds=review_timeout,
    )


def test_run_pause_resume_with_edited_outline():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    ai = _ai(review_outline=True)
    status = InMemoryStatusManager()
    orch = _make_orch(ai, r, status)

    out: dict = {}
    t = threading.Thread(target=lambda: out.update(orch.run()))
    t.start()

    edited = {
        "h1": "Изменённый заголовок",
        "sections": [{"section_id": "s0", "title": "Новая секция"}],
        "faq_section": {"enabled": True, "questions": ["q?"]},
    }
    publisher = PipelineControl(r, ai.article_id)
    deadline = time.time() + 5
    while time.time() < deadline and t.is_alive():
        publisher.confirm_review({"outline": edited})
        time.sleep(0.05)
    t.join(timeout=3)

    assert not t.is_alive()
    assert out["outline"].h1 == "Изменённый заголовок"  # resume применил правку
    for st in (
        ArticleStatus.INPUT_VALIDATED.value,
        ArticleStatus.SERP_DONE.value,
        ArticleStatus.COMPETITOR_ANALYSIS_DONE.value,
        ArticleStatus.BRIEF_DONE.value,
        ArticleStatus.OUTLINE_DONE.value,
        ArticleStatus.SECTIONS_IN_PROGRESS.value,
    ):
        assert st in status.statuses

    hist = EventEmitter(r, ai.article_id).history()
    types = [e["type"] for e in hist]
    assert types.count("step_started") == 5
    assert types.count("step_finished") == 5
    # step_finished несёт step_number (фикс: раньше терялся)
    finished = [e for e in hist if e["type"] == "step_finished"]
    assert all(isinstance(e["data"].get("step_number"), int) for e in finished)
    assert "review_ready" in types
    assert "cost_update" in types
    # event_id монотонны и последовательны
    assert [e["event_id"] for e in hist] == list(range(1, len(hist) + 1))


def test_review_timeout_finishes_with_status():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    ai = _ai(review_outline=True)
    status = InMemoryStatusManager()
    orch = _make_orch(ai, r, status, review_timeout=0.2)

    result = orch.run()  # никто не подтверждает ревью
    assert result.get("aborted") == "review_timeout"
    assert status.statuses[-1] == ArticleStatus.REVIEW_TIMEOUT.value
    types = [e["type"] for e in EventEmitter(r, ai.article_id).history()]
    assert "aborted" in types


def test_no_review_runs_straight_through():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    ai = _ai(review_outline=False)
    status = InMemoryStatusManager()
    result = _make_orch(ai, r, status).run()
    assert "outline" in result
    assert status.statuses[-1] == ArticleStatus.SECTIONS_IN_PROGRESS.value
    types = [e["type"] for e in EventEmitter(r, ai.article_id).history()]
    assert "review_ready" not in types


def test_stop_signal_aborts():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    ai = _ai(review_outline=False)
    status = InMemoryStatusManager()
    orch = _make_orch(ai, r, status)
    PipelineControl(r, ai.article_id).request_stop()  # стоп до старта

    result = orch.run()
    assert result.get("aborted") == "stopped_by_user"
    assert status.statuses[-1] == ArticleStatus.STOPPED_BY_USER.value
    types = [e["type"] for e in EventEmitter(r, ai.article_id).history()]
    assert "aborted" in types


def test_cost_tracked_across_steps():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    ai = _ai(review_outline=False)
    ct = CostTracker()
    _make_orch(ai, r, InMemoryStatusManager(), cost=ct).run()
    assert ct.article_cost > 0
    assert len(ct.calls) == 4  # competitor, lsi, brief, outline (SERP из fixture)
