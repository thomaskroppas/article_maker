"""final_qa_agent — шаг 12 (ТЗ §6.15, §6.16, §9.5).

Гибрид: 6 метрик кодом (metrics.py) + 3 субъективные LLM (brief_alignment,
intent_coverage, factuality). Итог — взвешенная сумма. Правило-предохранитель
factuality: >20% mismatches → factuality ≤ 50 и статус ≤ pass_with_warnings.
"""

from __future__ import annotations

from typing import Optional

from ..agents.base import BaseAgent
from ..constants import QA_SCORE_PASS, QA_SCORE_WARN
from ..schemas import CriteriaScores, FactCheckReport, QAResult, QAWarnings
from .metrics import calc_code_metrics, count_external_links

# Веса критериев — ТЗ §6.15 (НЕ менять).
WEIGHTS = {
    "brief_alignment": 0.20,
    "completeness": 0.20,
    "intent_coverage": 0.15,
    "keyword_usage": 0.10,
    "lsi_coverage": 0.05,
    "readability": 0.10,
    "structure": 0.10,
    "factuality": 0.05,
    "length_control": 0.05,
}


class FinalQAAgent(BaseAgent):
    agent_name = "final_qa_agent"

    def run(self, *, main_keyword, required_elements, target_word_count,
            brief_summary, competitor_summary, full_draft, code_metrics_summary) -> dict:
        resp = self._call(
            {
                "main_keyword": main_keyword,
                "required_elements": ", ".join(required_elements),
                "target_word_count": str(target_word_count),
                "brief_summary": brief_summary,
                "competitor_summary": competitor_summary,
                "full_draft": full_draft,
                "code_metrics_summary": code_metrics_summary,
            }
        )
        data = self._parse_json(resp.text)
        return data if isinstance(data, dict) else {}


def _factuality_safeguard(llm_factuality: float, report: Optional[FactCheckReport]) -> tuple[float, bool, list[str]]:
    """Возвращает (factuality, cap_to_warnings, critical_warnings) по §9.5."""
    if not report or report.total_statements == 0:
        return llm_factuality, False, []
    rate = report.mismatches / report.total_statements
    crit = [
        f"Fact mismatch: «{r.statement.text}» — внешн.: {r.external_value}"
        for r in report.results
        if r.status == "mismatch"
    ]
    if rate > 0.20:
        return min(llm_factuality, 50.0), True, crit  # ≤ pass_with_warnings
    if rate >= 0.10:
        return min(llm_factuality, 70.0), False, crit
    return llm_factuality, False, []


def run_final_qa(
    article_markdown: str,
    article_input,
    brief,
    outline,
    competitor_report,
    fact_check_report: Optional[FactCheckReport],
    llm,
) -> QAResult:
    ai = article_input
    target = sum(s.target_word_count for s in outline.sections)
    cm = calc_code_metrics(
        article_markdown,
        target_words=target,
        main_keyword=ai.main_keyword,
        secondary_keywords=ai.secondary_keywords,
        required_elements=ai.required_elements,
        lsi_keywords=brief.lsi_keywords,
        language=ai.language,
    )

    code_summary = (
        f"length_control={cm.length_control}, completeness={cm.completeness}, "
        f"keyword_usage={cm.keyword_usage}, lsi_coverage={cm.lsi_coverage}, "
        f"structure={cm.structure}, readability={cm.readability}"
    )
    llm_scores = FinalQAAgent(llm).run(
        main_keyword=ai.main_keyword,
        required_elements=ai.required_elements,
        target_word_count=target,
        brief_summary=brief.goal,
        competitor_summary=", ".join(competitor_report.must_have_topics),
        full_draft=article_markdown,
        code_metrics_summary=code_summary,
    )

    brief_alignment = float(llm_scores.get("brief_alignment", 0))
    intent_coverage = float(llm_scores.get("intent_coverage", 0))
    llm_factuality = float(llm_scores.get("factuality", 0))
    factuality, cap_warn, crit = _factuality_safeguard(llm_factuality, fact_check_report)

    scores = CriteriaScores(
        brief_alignment=brief_alignment,
        completeness=cm.completeness,
        intent_coverage=intent_coverage,
        keyword_usage=cm.keyword_usage,
        lsi_coverage=cm.lsi_coverage,
        readability=cm.readability,
        structure=cm.structure,
        factuality=factuality,
        length_control=cm.length_control,
    )
    score = round(sum(getattr(scores, k) * w for k, w in WEIGHTS.items()))

    # warnings по важности (§6.15, FR-16)
    warnings = QAWarnings(critical=list(crit))
    fail_reasons: list[str] = []
    if "weaved_sources" in ai.required_elements and count_external_links(article_markdown) < 3:
        warnings.medium.append("weaved_sources: <3 внешних ссылок в тексте")
    if cm.length_control < 60:
        warnings.medium.append(f"length_control низкий ({cm.length_control}): объём далёк от целевого")
    if cm.readability < 70:
        warnings.minor.append(f"readability {cm.readability}: длинные/короткие предложения")

    # статус (§6.2.1) + предохранитель
    if score >= QA_SCORE_PASS:
        status = "pass"
    elif score >= QA_SCORE_WARN:
        status = "pass_with_warnings"
    else:
        status = "fail"
        fail_reasons.append(f"score {score} < {QA_SCORE_WARN}")
    if cap_warn and status == "pass":
        status = "pass_with_warnings"  # §9.5: >20% mismatches → максимум pass_with_warnings

    return QAResult(
        status=status,
        score=score,
        criteria_scores=scores,
        warnings=warnings,
        fail_reasons=fail_reasons,
        recommendation=llm_scores.get("recommendation", ""),
    )
