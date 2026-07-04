"""competitor_analysis_agent — шаг 2 (ТЗ §6.4, §7.3.1)."""

from __future__ import annotations

from typing import Optional

from ..schemas import CompetitorAnalysisReport, SerpBundle, WordCountRange
from ..serp.aggregation import robust_average
from .base import BaseAgent
from .cache import AgentCache

_SUMMARY_WORDS = 300


def compute_ranges(bundle: SerpBundle) -> tuple[WordCountRange, WordCountRange, list[str]]:
    """word_count_range и h2_count_range из SERP (trimmed mean + fallback §6.4)."""
    pages = bundle.pages
    if not pages:
        empty = WordCountRange()
        return empty, empty, []
    wcs = [p.word_count for p in pages]
    h2s = [len(p.headings.h2) for p in pages]
    wc_avg = robust_average(wcs)
    h2_avg = robust_average(h2s)
    warnings = sorted({w for w in (wc_avg.warning, h2_avg.warning) if w})
    word_range = WordCountRange(
        min=min(wcs), avg_trimmed=wc_avg.avg, max=max(wcs), per_page=wcs
    )
    h2_range = WordCountRange(
        min=min(h2s), avg_trimmed=h2_avg.avg, max=max(h2s), per_page=h2s
    )
    return word_range, h2_range, warnings


def _competitor_digest(bundle: SerpBundle) -> str:
    """Выжимка для промпта: title, H1/H2/H3 и первые 300 слов текста на URL (§6.4)."""
    blocks = []
    for p in bundle.pages:
        first_words = " ".join(p.content.split()[:_SUMMARY_WORDS])
        blocks.append(
            f"## {p.title}\n"
            f"H1: {'; '.join(p.headings.h1)}\n"
            f"H2: {'; '.join(p.headings.h2)}\n"
            f"H3: {'; '.join(p.headings.h3)}\n"
            f"{first_words}"
        )
    return "\n\n".join(blocks)


class CompetitorAnalysisAgent(BaseAgent):
    agent_name = "competitor_analysis_agent"

    def __init__(self, llm, cache: Optional[AgentCache] = None):
        super().__init__(llm)
        self.cache = cache
        self.warnings: list[str] = []

    def run(self, article_input, serp_bundle: SerpBundle) -> CompetitorAnalysisReport:
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
                    "main_keyword": ai.main_keyword,
                    "analysis_csv": serp_bundle.analysis_csv,
                    "contents_txt": _competitor_digest(serp_bundle),
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

        report = CompetitorAnalysisReport.model_validate(data)
        # Диапазоны длины/H2 — авторитетно из кода (§6.4), не из LLM.
        word_range, h2_range, self.warnings = compute_ranges(serp_bundle)
        report.word_count_range = word_range
        report.h2_count_range = h2_range
        return report
