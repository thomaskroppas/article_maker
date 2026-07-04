"""T-10: финальный QA (метрики, пороги, предохранитель) + метаданные."""

from __future__ import annotations

import json

from app.agents.metadata import MetadataAgent
from app.llm import MockLLMClient
from app.paths import reference_dir
from app.qa import WEIGHTS, calc_code_metrics
from app.qa.final_qa import _factuality_safeguard, run_final_qa
from app.schemas import (
    ArticleInput,
    Brief,
    CompetitorAnalysisReport,
    FactCheckReport,
    FactCheckResult,
    FactStatement,
    FullDraft,
    Outline,
)


def _ref(name):
    return json.loads((reference_dir() / name).read_text(encoding="utf-8"))


def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 5) == 1.0


def test_qa_score_within_5_of_reference():
    """DoD: QA на article.md в пределах ±5 от qa_result.json (89)."""
    md = (reference_dir() / "article.md").read_text(encoding="utf-8")
    ai = ArticleInput.model_validate(_ref("article_input.json"))
    brief = Brief.model_validate(_ref("brief.json"))
    outline = Outline.model_validate(_ref("outline.json"))
    report = CompetitorAnalysisReport.model_validate(_ref("competitor_analysis_report.json"))

    # LLM-метрики берём из reference qa_result (эмулируем final_qa_agent).
    ref_qa = _ref("qa_result.json")["criteria_scores"]
    llm = MockLLMClient(responses={"final_qa_agent": json.dumps({
        "brief_alignment": ref_qa["brief_alignment"],
        "intent_coverage": ref_qa["intent_coverage"],
        "factuality": ref_qa["factuality"],
    })})
    qa = run_final_qa(md, ai, brief, outline, report, None, llm)
    assert abs(qa.score - 89) <= 5, f"score {qa.score} вне ±5 от 89"


def test_code_metrics_match_reference_dimensions():
    md = (reference_dir() / "article.md").read_text(encoding="utf-8")
    ai = ArticleInput.model_validate(_ref("article_input.json"))
    brief = Brief.model_validate(_ref("brief.json"))
    outline = Outline.model_validate(_ref("outline.json"))
    cm = calc_code_metrics(
        md, target_words=sum(s.target_word_count for s in outline.sections),
        main_keyword=ai.main_keyword, secondary_keywords=ai.secondary_keywords,
        required_elements=ai.required_elements, lsi_keywords=brief.lsi_keywords, language="ru",
    )
    # три «лёгкие» метрики должны совпасть с reference (100)
    assert cm.keyword_usage == 100.0
    assert cm.lsi_coverage == 100.0
    assert cm.structure == 100.0


def _fc(total, mismatches):
    results = []
    for i in range(total):
        st = FactStatement(text="t", type="numeric", subject="s", value_in_article="1")
        status = "mismatch" if i < mismatches else "verified"
        results.append(FactCheckResult(statement=st, status=status, external_value="2", confidence=0.8))
    return FactCheckReport(total_statements=total, verified=total - mismatches,
                           mismatches=mismatches, uncertain=0, results=results, checked_at="2026-07-04T00:00:00Z")


def test_factuality_safeguard_over_20pct():
    fact, cap, crit = _factuality_safeguard(90.0, _fc(10, 3))  # 30% mismatch
    assert fact <= 50.0
    assert cap is True
    assert len(crit) == 3


def test_factuality_safeguard_10_to_20pct():
    fact, cap, crit = _factuality_safeguard(90.0, _fc(10, 1))  # 10%
    assert fact <= 70.0
    assert cap is False


def test_factuality_safeguard_under_10pct():
    fact, cap, crit = _factuality_safeguard(90.0, _fc(20, 1))  # 5%
    assert fact == 90.0
    assert cap is False and crit == []


def test_safeguard_caps_status_to_warnings():
    """>20% mismatches → даже при высоком score статус не выше pass_with_warnings."""
    md = (reference_dir() / "article.md").read_text(encoding="utf-8")
    ai = ArticleInput.model_validate(_ref("article_input.json"))
    brief = Brief.model_validate(_ref("brief.json"))
    outline = Outline.model_validate(_ref("outline.json"))
    report = CompetitorAnalysisReport.model_validate(_ref("competitor_analysis_report.json"))
    llm = MockLLMClient(responses={"final_qa_agent": json.dumps(
        {"brief_alignment": 95, "intent_coverage": 95, "factuality": 95}
    )})
    qa = run_final_qa(md, ai, brief, outline, report, _fc(10, 5), llm)  # 50% mismatch
    assert qa.status != "pass"
    assert qa.warnings.critical  # mismatches в critical


def test_thresholds_pass_warn_fail():
    from app.constants import QA_SCORE_PASS, QA_SCORE_WARN

    assert QA_SCORE_PASS == 85 and QA_SCORE_WARN == 70


def test_metadata_builds_final_package():
    ai = ArticleInput.model_validate(_ref("article_input.json"))
    draft = FullDraft(h1="Байкал", content_markdown="# Байкал\n\nтекст", section_count=1)
    from app.schemas import QAResult

    qa = QAResult.model_validate(_ref("qa_result.json"))
    fp_json = json.dumps(_ref("final_package.json"))
    fp = MetadataAgent(MockLLMClient(responses={"metadata_agent": fp_json})).run(ai, draft, qa)
    assert fp.article_id == ai.article_id  # проставлен из ai
    assert fp.article_markdown  # добран из draft/ответа
    assert fp.meta_title
