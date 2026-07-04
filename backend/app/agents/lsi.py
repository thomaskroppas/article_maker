"""lsi_agent — шаг 3 (ТЗ §6.5, §7.3.2): 15-25 английских LSI-слов для картинок."""

from __future__ import annotations

from typing import Optional

from ..schemas import CompetitorAnalysisReport
from .base import BaseAgent
from .cache import AgentCache


def _normalize_lsi(parsed) -> list[str]:
    if isinstance(parsed, dict):
        parsed = parsed.get("lsi_keywords", [])
    if not isinstance(parsed, list):
        return []
    return [str(x).strip() for x in parsed if str(x).strip()]


class LSIAgent(BaseAgent):
    agent_name = "lsi_agent"

    def __init__(self, llm, cache: Optional[AgentCache] = None):
        super().__init__(llm)
        self.cache = cache

    def run(self, article_input, report: CompetitorAnalysisReport) -> list[str]:
        ai = article_input
        cached = (
            self.cache.get(
                self.agent_name, ai.article_title, ai.main_keyword, ai.secondary_keywords
            )
            if self.cache
            else None
        )
        if cached is not None:
            keywords = _normalize_lsi(cached)
        else:
            resp = self._call(
                {
                    "article_title": ai.article_title,
                    "main_keyword": ai.main_keyword,
                    "secondary_keywords": ", ".join(ai.secondary_keywords),
                    "common_h2": "; ".join(t.title for t in report.common_h2_titles),
                    "competitor_titles": "; ".join(report.must_have_topics),
                    "content_gaps": "; ".join(g.title for g in report.content_gaps),
                }
            )
            keywords = _normalize_lsi(self._parse_json(resp.text))
            if self.cache:
                self.cache.set(
                    self.agent_name,
                    ai.article_title,
                    ai.main_keyword,
                    ai.secondary_keywords,
                    keywords,
                )

        # Дедуп против main/secondary (ТЗ §7.3.2), без дублей, порядок сохранён.
        banned = {ai.main_keyword.lower(), *(s.lower() for s in ai.secondary_keywords)}
        out: list[str] = []
        for kw in keywords:
            low = kw.lower()
            if low in banned or low in {o.lower() for o in out}:
                continue
            out.append(kw)
        return out
