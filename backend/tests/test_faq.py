"""T-8: FAQ — генерация, вставка, дедупликация (§6.12, FR-18)."""

from __future__ import annotations

from app.agents import insert_faq, run_faq_stage
from app.agents.faq_writer import _dedup_questions
from app.llm import MockLLMClient
from app.schemas import Brief, FaqSection, Outline, SectionSpec, WordCountRange

FAQ_BLOCK = "## FAQ\n**Где Байкал?**\nВ Сибири."


def _brief():
    return Brief.model_validate(
        {"word_count_range": WordCountRange(), "keywords": {"main": "байкал"},
         "data_handling_rules": {}}
    )


class _AI:
    article_title = "Байкал"
    main_keyword = "байкал"
    language = "ru"


def _outline(enabled, questions, extra_faq_section=False):
    sections = [SectionSpec(section_id="s0", title="Введение")]
    if extra_faq_section:
        sections.append(SectionSpec(section_id="s5", title="FAQ — частые вопросы"))
    return Outline(h1="H", sections=sections, faq_section=FaqSection(enabled=enabled, questions=questions))


def test_faq_skipped_when_already_in_sections():
    # FR-18: если FAQ-секция уже есть в outline — не дублируем.
    outline = _outline(enabled=True, questions=["Q1?"], extra_faq_section=True)
    md = "# T\n\n## Введение\nтекст"
    out = run_faq_stage(_AI(), _brief(), outline, md, MockLLMClient(responses={"faq_writer_agent": FAQ_BLOCK}))
    assert out == md  # без изменений


def test_faq_skipped_when_disabled():
    outline = _outline(enabled=False, questions=["Q1?"])
    md = "# T\n\n## Введение\nтекст"
    out = run_faq_stage(_AI(), _brief(), outline, md, MockLLMClient(responses={"faq_writer_agent": FAQ_BLOCK}))
    assert out == md


def test_faq_added_when_enabled():
    outline = _outline(enabled=True, questions=["Где Байкал?", "Где Байкал?", "Глубина?"])
    md = "# T\n\n## Введение\nтекст"
    out = run_faq_stage(_AI(), _brief(), outline, md, MockLLMClient(responses={"faq_writer_agent": FAQ_BLOCK}))
    assert "## FAQ" in out


def test_dedup_questions():
    assert _dedup_questions(["A?", "a?", " A? ", "B?", ""]) == ["A?", "B?"]


def test_insert_faq_before_conclusion():
    md = "# T\n\n## Введение\nтекст\n\n## Заключение\nитоги"
    out = insert_faq(md, FAQ_BLOCK)
    assert out.index("## FAQ") < out.index("## Заключение")


def test_insert_faq_appends_when_no_conclusion():
    md = "# T\n\n## Введение\nтекст"
    out = insert_faq(md, FAQ_BLOCK)
    assert out.rstrip().endswith("В Сибири.")
