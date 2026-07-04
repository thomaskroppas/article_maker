"""brief_agent — шаг 4 (ТЗ §6.6, §7.3.3)."""

from __future__ import annotations

from typing import Optional

from ..schemas import Brief, CompetitorAnalysisReport, DataHandlingRules, DataSensitivity
from .base import BaseAgent
from .cache import AgentCache

MULTIPLIERS = {"shorter_top": 0.7, "match_top": 1.0, "longer_top": 1.3}


def compute_target_word_count(article_input, report: CompetitorAnalysisReport) -> int:
    """Целевая длина по стратегии (ТЗ §6.6)."""
    ai = article_input
    if ai.length_strategy == "custom":
        return int(ai.target_word_count or 0)
    avg = report.word_count_range.avg_trimmed
    return round(avg * MULTIPLIERS.get(ai.length_strategy, 1.0))


def build_data_handling_rules(ds: DataSensitivity) -> DataHandlingRules:
    """Из data_sensitivity (ТЗ §7.3.3): volatile → приблизительные формулировки."""
    if ds.has_volatile_data:
        return DataHandlingRules(avoid_exact_dates=True, use_approximate_language=True)
    return DataHandlingRules()


class BriefAgent(BaseAgent):
    agent_name = "brief_agent"

    def __init__(self, llm, cache: Optional[AgentCache] = None):
        super().__init__(llm)
        self.cache = cache

    def run(
        self,
        article_input,
        report: CompetitorAnalysisReport,
        lsi_keywords: Optional[list[str]] = None,
    ) -> Brief:
        ai = article_input
        target = compute_target_word_count(ai, report)

        cached = (
            self.cache.get(
                self.agent_name, ai.article_title, ai.main_keyword, ai.secondary_keywords
            )
            if self.cache
            else None
        )
        if cached is not None:
            data = cached
        else:
            resp = self._call(
                {
                    "article_title": ai.article_title,
                    "article_type": ai.article_type,
                    "competitor_analysis_json": report.model_dump_json(),
                    "difficulty": ai.difficulty,
                    "forbidden_words": ", ".join(ai.forbidden_words),
                    "geo": ai.geo,
                    "intent": ai.intent,
                    "language": ai.language,
                    "main_keyword": ai.main_keyword,
                    "optional_notes": ai.optional_notes or "",
                    "required_elements": ", ".join(ai.required_elements),
                    "secondary_keywords": ", ".join(ai.secondary_keywords),
                    "style_archetype": ai.style_archetype,
                    "target_word_count": str(target),
                }
            )
            data = self._parse_json(resp.text)
            if self.cache:
                self.cache.set(
                    self.agent_name,
                    ai.article_title,
                    ai.main_keyword,
                    ai.secondary_keywords,
                    data,
                )

        brief = Brief.model_validate(data)
        # Авторитетно из кода (§6.6, §7.3.3):
        brief.word_count_target = target
        brief.data_handling_rules = build_data_handling_rules(report.data_sensitivity)
        if lsi_keywords is not None:
            brief.lsi_keywords = lsi_keywords
        return brief
