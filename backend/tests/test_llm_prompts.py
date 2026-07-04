"""T-4: рендер промптов всех 13 агентов + безопасность к литеральному '$' (риск 22.8)."""

from __future__ import annotations

import re

import pytest

from app.llm.prompt_loader import PROMPT_AGENTS, load_prompt, render_prompt

# Полный набор плейсхолдеров по всем промптам (фиктивные значения).
ALL_VARS = {
    v: f"<{v}>"
    for v in [
        "analysis_csv", "archetypes_list", "article_markdown", "suggested_sources",
        "article_summary", "article_title",
        "article_type", "author_block", "brief_json", "brief_summary",
        "code_metrics_summary", "common_h2", "competitor_analysis_json",
        "competitor_analysis_summary", "competitor_summary", "competitor_titles",
        "content_gaps", "contents_txt", "difficulty", "fix_instructions",
        "forbidden_words", "full_draft", "geo", "intent", "language",
        "lsi_keywords", "main_keyword", "notes", "optional_notes",
        "previous_sections", "qa_score", "qa_status", "qa_warnings",
        "queries_list", "questions", "required_elements", "review_issues",
        "secondary_keywords", "section_draft", "section_id", "section_keywords",
        "section_level", "section_must_cover", "section_purpose",
        "section_target_words", "section_title", "style_archetype",
        "target_word_count", "tone", "topic", "writer_name",
    ]
}


def test_prompt_agents_count():
    # 13 существующих + sources_weaver + fact_checker (написаны в T-9)
    assert len(PROMPT_AGENTS) == 15


@pytest.mark.parametrize("agent", PROMPT_AGENTS)
def test_render_does_not_crash(agent):
    out = render_prompt(agent, ALL_VARS)
    assert isinstance(out, str)
    assert out.strip()


@pytest.mark.parametrize("agent", PROMPT_AGENTS)
def test_provided_placeholders_substituted(agent):
    raw = load_prompt(agent)
    provided = set(re.findall(r"\$\{?([a-zA-Z_][a-zA-Z0-9_]*)\}?", raw)) & set(ALL_VARS)
    out = render_prompt(agent, ALL_VARS)
    for var in provided:
        assert f"<{var}>" in out, f"{agent}: переменная {var} не подставилась"


def test_literal_dollar_does_not_crash():
    # safe_substitute не должен падать на литеральном '$' (например '$5.00', '$-x')
    # и должен подставлять валидные переменные рядом.
    from string import Template

    text = "Цена $5.00, режим $-x, значение ${main_keyword} и $main_keyword"
    out = Template(text).safe_substitute({"main_keyword": "байкал"})
    assert "байкал" in out
    assert "$5.00" in out  # литерал сохранён
    assert "$-x" in out


def test_missing_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_agent")
