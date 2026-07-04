"""T-6: шаги 1–5 end-to-end на MockLLM; структура совпадает с reference_article."""

from __future__ import annotations

import json

from app.agents import AgentCache, LSIAgent, OutlineAgent, run_analysis_stage
from app.agents.brief import BriefAgent
from app.llm import CostTracker, MockLLMClient
from app.paths import fixtures_dir, reference_dir
from app.schemas import ArticleInput, Brief, CompetitorAnalysisReport, Outline
from app.serp.aggregation import robust_average
from app.serp.service import SerpConfig, SerpService


def _ai(**over):
    base = dict(
        article_title="Где находится Байкал",
        main_keyword="байкал где находится",
        secondary_keywords=["байкал дно", "где находится байкал"],
        language="ru",
        geo="ru",
        intent="informational",
        article_type="informational",
        difficulty="easy",
        style_archetype="expert_clear",
        required_elements=["faq"],
    )
    base.update(over)
    return ArticleInput.model_validate(base)


def _serp_bundle():
    fx = str(fixtures_dir() / "serp_bundle_example.json")
    return SerpService().get_serp(_ai(serp_json_path=fx), SerpConfig())


def test_analysis_stage_end_to_end():
    bundle = _serp_bundle()
    result = run_analysis_stage(_ai(), bundle, MockLLMClient())

    # Все выходы валидны схемами §13.
    assert isinstance(result.competitor_report, CompetitorAnalysisReport)
    assert isinstance(result.brief, Brief)
    assert isinstance(result.outline, Outline)
    assert isinstance(result.lsi_keywords, list) and result.lsi_keywords

    # Диапазоны длины — из SERP (код авторитетен, §6.4).
    wcs = [p.word_count for p in bundle.pages]
    assert result.competitor_report.word_count_range.per_page == wcs
    assert result.competitor_report.word_count_range.avg_trimmed == robust_average(wcs).avg

    # Brief.word_count_target = round(avg_trimmed) при match_top.
    assert result.brief.word_count_target == round(
        result.competitor_report.word_count_range.avg_trimmed
    )
    # lsi проброшены в brief.
    assert result.brief.lsi_keywords == result.lsi_keywords


def test_structure_matches_reference_article():
    """Ключи выходов совпадают со структурой reference_article/*.json."""
    bundle = _serp_bundle()
    result = run_analysis_stage(_ai(), bundle, MockLLMClient())
    ref = reference_dir()

    def ref_keys(name):
        return set(json.loads((ref / name).read_text(encoding="utf-8")).keys())

    assert set(result.competitor_report.model_dump().keys()) >= (
        ref_keys("competitor_analysis_report.json")
        - {"content_format", "structure_patterns", "common_sections"}
    )
    assert set(result.brief.model_dump().keys()) == ref_keys("brief.json")
    assert set(result.outline.model_dump().keys()) == ref_keys("outline.json")


def test_agent_cache_avoids_second_llm_call(tmp_path):
    bundle = _serp_bundle()
    cache = AgentCache(tmp_path)
    ct1 = CostTracker()
    run_analysis_stage(_ai(), bundle, MockLLMClient(cost_tracker=ct1), cache)
    assert len(ct1.calls) == 4  # competitor, lsi, brief, outline

    ct2 = CostTracker()
    run_analysis_stage(_ai(), bundle, MockLLMClient(cost_tracker=ct2), cache)
    assert len(ct2.calls) == 0  # всё из кэша


def test_outline_faq_warning_when_missing():
    from app.schemas import Outline, SectionSpec

    result = run_analysis_stage(_ai(), _serp_bundle(), MockLLMClient())
    brief = result.brief
    brief.required_elements = ["faq"]

    no_faq = Outline(h1="H", sections=[SectionSpec(section_id="s0", title="Введение")])
    oa = OutlineAgent(MockLLMClient(responses={"outline_agent": no_faq.model_dump_json()}))
    oa.run(_ai(), brief, result.competitor_report)
    assert any("faq" in w.lower() for w in oa.warnings)


def test_outline_length_warning():
    from app.schemas import Outline, SectionSpec

    result = run_analysis_stage(_ai(), _serp_bundle(), MockLLMClient())
    brief = result.brief
    brief.word_count_target = 2000
    tiny = Outline(
        h1="H",
        sections=[SectionSpec(section_id="s0", title="Введение", target_word_count=100)],
    )
    oa = OutlineAgent(MockLLMClient(responses={"outline_agent": tiny.model_dump_json()}))
    oa.run(_ai(), brief, result.competitor_report)
    assert any("20%" in w for w in oa.warnings)
