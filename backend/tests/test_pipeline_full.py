"""T-10: полный пайплайн (шаги 1–13) на MockLLM через оркестратор."""

from __future__ import annotations

import json

import fakeredis

from app.db.enums import ArticleStatus
from app.llm import MockLLMClient
from app.orchestrator.events import EventEmitter
from app.orchestrator.pipeline import PipelineOrchestrator
from app.orchestrator.control import PipelineControl
from app.orchestrator.status import InMemoryStatusManager
from app.paths import fixtures_dir
from app.schemas import ArticleInput
from app.serp.service import SerpConfig, SerpService


def _ai():
    return ArticleInput.model_validate(dict(
        article_title="Где находится Байкал",
        main_keyword="байкал где находится",
        secondary_keywords=["байкал дно"],
        language="ru", geo="ru",
        intent="informational", article_type="informational",
        difficulty="easy", style_archetype="expert_clear",
        required_elements=["faq", "quick_answer", "conclusion"],
        review_outline=False,
        serp_json_path=str(fixtures_dir() / "serp_bundle_example.json"),
    ))


def _fake_lookup(stmt, lang):
    return {"value": "Озеро Байкал в Сибири", "source_url": "http://wiki/b", "source_name": "test"}


def test_full_pipeline_to_final_package():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    ai = _ai()
    status = InMemoryStatusManager()
    orch = PipelineOrchestrator(
        ai,
        emitter=EventEmitter(r, ai.article_id),
        control=PipelineControl(r, ai.article_id, poll_interval=0.05),
        status=status,
        llm=MockLLMClient(),
        serp_service=SerpService(),
        serp_config=SerpConfig(),
        fact_lookup_fn=_fake_lookup,  # офлайн, без Wikipedia
        url_alive=lambda u: True,
    )
    result = orch.run()

    # финальные артефакты
    assert "final_package" in result and "qa_result" in result
    assert result["final_package"].article_id == ai.article_id

    # статусы прошли до терминального (Приложение C)
    for st in (
        ArticleStatus.DRAFT_READY.value,
        ArticleStatus.IMAGES_DONE.value,
        ArticleStatus.SOURCES_DONE.value,
        ArticleStatus.FACT_CHECK_DONE.value,
        ArticleStatus.QA_DONE.value,
    ):
        assert st in status.statuses
    assert status.statuses[-1] in (
        ArticleStatus.COMPLETED.value,
        ArticleStatus.READY_FOR_MANUAL_REVIEW_WITH_WARNINGS.value,
        ArticleStatus.READY_FOR_MANUAL_REVIEW.value,
    )

    # событие finished с qa_result + final_package
    hist = EventEmitter(r, ai.article_id).history()
    types = [e["type"] for e in hist]
    assert "finished" in types
    finished = next(e for e in hist if e["type"] == "finished")
    assert "qa_result" in finished["data"]
    assert "final_package" in finished["data"]
    # все 13 шагов отметились
    assert types.count("step_started") == 13
    assert types.count("step_finished") == 13
