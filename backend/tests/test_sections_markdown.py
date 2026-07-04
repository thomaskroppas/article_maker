"""T-8: секции (Writer→Critic→Editor) + сборка markdown."""

from __future__ import annotations

import json

from app.agents import assemble_draft, run_section, run_sections_stage
from app.agents.critic import CriticAgent
from app.agents.editor import EditorAgent
from app.agents.writer import WriterAgent
from app.llm import LLMResponse, MockLLMClient
from app.llm.client import BaseLLMClient
from app.paths import fixtures_dir, reference_dir
from app.schemas import Brief, CompetitorAnalysisReport, Outline

CRITIC_PASS = json.dumps(
    {"overall_score": 82, "per_criterion": {}, "issues": [], "suggestions": []}
)
CRITIC_FAIL = json.dumps(
    {"overall_score": 40, "per_criterion": {}, "issues": ["слабо"], "suggestions": ["усиль"]}
)
WRITER_MD = "## Секция\nТело секции с фактами и цифрами про Байкал.\n<!-- SUMMARY: Байкал глубина 1642 м -->"


class ScriptedLLM(BaseLLMClient):
    """Возвращает по агенту очередь ответов (последний повторяется)."""

    def __init__(self, scripts: dict[str, list[str]]):
        super().__init__()
        self.scripts = scripts
        self.calls: list[str] = []

    def call(self, agent_name, prompt, system_prompt=None):
        self.calls.append(agent_name)
        q = self.scripts.get(agent_name, [""])
        text = q.pop(0) if len(q) > 1 else q[0]
        return LLMResponse(text=text, model="x")


def _fx(name):
    return json.loads((fixtures_dir() / name).read_text(encoding="utf-8"))


def _brief():
    return Brief.model_validate(_fx("brief_example.json"))


def _report():
    return CompetitorAnalysisReport.model_validate(_fx("competitor_analysis_example.json"))


def _outline():
    return Outline.model_validate(_fx("outline_example.json"))


class _AI:
    article_title = "Байкал"
    main_keyword = "байкал"
    secondary_keywords = ["дно"]
    language = "ru"
    style_archetype = "expert_clear"
    enable_section_critic = True


def test_full_draft_structure_matches_reference():
    llm = MockLLMClient(responses={"writer_agent": WRITER_MD, "critic_agent": CRITIC_PASS})
    outline = _outline()
    result = run_sections_stage(_AI(), _brief(), _report(), outline, llm)
    draft = result.draft

    ref_keys = set(json.loads((reference_dir() / "full_draft.json").read_text("utf-8")))
    assert set(draft.model_dump().keys()) == ref_keys
    assert draft.section_count == len(outline.sections)
    # §13.5 SectionFinal содержит section_id/title/content (+ iterations сверх reference)
    assert {"section_id", "title", "content"} <= set(draft.sections[0].model_dump().keys())
    # SUMMARY-маркер не попал в готовый текст
    assert "SUMMARY" not in draft.content_markdown
    assert draft.h1 == outline.h1
    assert draft.word_count > 0


def test_summary_threaded_to_next_section():
    llm = MockLLMClient(responses={"writer_agent": WRITER_MD, "critic_agent": CRITIC_PASS})
    res = run_sections_stage(_AI(), _brief(), _report(), _outline(), llm)
    # summary извлечён из каждой секции
    assert all(r.summary for r in res.section_results)


def test_critic_loop_editor_then_pass():
    from app.schemas import SectionSpec

    llm = ScriptedLLM(
        {
            "writer_agent": [WRITER_MD],
            "critic_agent": [CRITIC_FAIL, CRITIC_PASS],  # fail → editor → pass
            "editor_agent": ["## Секция\nУлучшенный текст."],
        }
    )
    spec = SectionSpec(section_id="s1", title="Секция", target_word_count=200)
    res = run_section(
        spec, _AI(), _brief(), _report(), [],
        WriterAgent(llm), CriticAgent(llm), EditorAgent(llm), enable_critic=True,
    )
    assert res.iterations == 2  # writer + 1 editor
    assert not res.is_weak
    assert "editor_agent" in llm.calls


def test_critic_max_iterations_marks_weak():
    from app.schemas import SectionSpec

    llm = ScriptedLLM(
        {
            "writer_agent": [WRITER_MD],
            "critic_agent": [CRITIC_FAIL],  # всегда fail
            "editor_agent": ["## Секция\nвсё ещё слабо"],
        }
    )
    spec = SectionSpec(section_id="s1", title="Секция", target_word_count=200)
    res = run_section(
        spec, _AI(), _brief(), _report(), [],
        WriterAgent(llm), CriticAgent(llm), EditorAgent(llm), enable_critic=True,
    )
    assert res.is_weak
    assert res.iterations == 3  # SECTION_MAX_ITERATIONS


def test_critic_disabled_single_pass():
    from app.schemas import SectionSpec

    ai = _AI()
    ai.enable_section_critic = False
    llm = ScriptedLLM({"writer_agent": [WRITER_MD]})
    spec = SectionSpec(section_id="s1", title="Секция", target_word_count=200)
    res = run_section(
        spec, ai, _brief(), _report(), [],
        WriterAgent(llm), CriticAgent(llm), EditorAgent(llm), enable_critic=False,
    )
    assert res.iterations == 1
    assert "critic_agent" not in llm.calls


def test_quick_answer_no_heading():
    from app.schemas import Outline, SectionSpec

    outline = Outline(
        h1="H1",
        sections=[
            SectionSpec(section_id="s0", title="quick_answer", level="H2"),
            SectionSpec(section_id="s1", title="Раздел", level="H2"),
        ],
    )
    draft = assemble_draft(outline, {"s0": "Краткий ответ.", "s1": "Тело раздела."})
    assert "## quick_answer" not in draft.content_markdown  # без заголовка
    assert "## Раздел" in draft.content_markdown
