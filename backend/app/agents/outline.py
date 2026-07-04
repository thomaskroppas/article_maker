"""outline_agent — шаг 5 (ТЗ §6.7, §7.3.4)."""

from __future__ import annotations

from typing import Optional

from ..schemas import Brief, CompetitorAnalysisReport, Outline
from .base import BaseAgent
from .cache import AgentCache

_LENGTH_TOLERANCE = 0.2


class OutlineAgent(BaseAgent):
    agent_name = "outline_agent"

    def __init__(self, llm, cache: Optional[AgentCache] = None):
        super().__init__(llm)
        self.cache = cache
        self.warnings: list[str] = []

    def run(
        self, article_input, brief: Brief, report: CompetitorAnalysisReport
    ) -> Outline:
        ai = article_input
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
                    "brief_json": brief.model_dump_json(),
                    "competitor_analysis_json": report.model_dump_json(),
                    "main_keyword": ai.main_keyword,
                    "required_elements": ", ".join(ai.required_elements),
                    "target_word_count": str(brief.word_count_target),
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

        outline = Outline.model_validate(data)
        self.warnings = []

        # Проверка длины (§6.7): сумма секций vs target, разница >20% → warning.
        total = sum(s.target_word_count for s in outline.sections)
        target = brief.word_count_target
        if target and abs(total - target) / target > _LENGTH_TOLERANCE:
            self.warnings.append(
                f"Сумма target_word_count секций ({total}) отличается от "
                f"word_count_target brief ({target}) более чем на 20%"
            )

        # Проверка FAQ (§7.3.4): required_elements содержит faq → нужен FAQ.
        if "faq" in brief.required_elements:
            has_faq = outline.faq_section.enabled or any(
                "faq" in s.title.lower() or "вопрос" in s.title.lower()
                for s in outline.sections
            )
            if not has_faq:
                self.warnings.append(
                    "required_elements содержит 'faq', но outline не содержит FAQ-секцию"
                )

        return outline
