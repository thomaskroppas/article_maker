"""Аналитическая стадия пайплайна — шаги 2–5 (ТЗ §6.4–6.7).

Тонкий раннер поверх агентов; полный оркестратор со статусами/событиями — T-7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..llm.client import BaseLLMClient
from ..schemas import Brief, CompetitorAnalysisReport, Outline, SerpBundle
from .brief import BriefAgent
from .cache import AgentCache
from .competitor import CompetitorAnalysisAgent
from .lsi import LSIAgent
from .outline import OutlineAgent


@dataclass
class AnalysisStageResult:
    serp_bundle: SerpBundle
    competitor_report: CompetitorAnalysisReport
    lsi_keywords: list[str]
    brief: Brief
    outline: Outline
    warnings: list[str] = field(default_factory=list)


def run_analysis_stage(
    article_input,
    serp_bundle: SerpBundle,
    llm: BaseLLMClient,
    agent_cache: Optional[AgentCache] = None,
) -> AnalysisStageResult:
    competitor = CompetitorAnalysisAgent(llm, agent_cache)
    report = competitor.run(article_input, serp_bundle)  # шаг 2

    lsi = LSIAgent(llm, agent_cache)
    lsi_keywords = lsi.run(article_input, report)  # шаг 3

    brief_agent = BriefAgent(llm, agent_cache)
    brief = brief_agent.run(article_input, report, lsi_keywords=lsi_keywords)  # шаг 4

    outline_agent = OutlineAgent(llm, agent_cache)
    outline = outline_agent.run(article_input, brief, report)  # шаг 5

    return AnalysisStageResult(
        serp_bundle=serp_bundle,
        competitor_report=report,
        lsi_keywords=lsi_keywords,
        brief=brief,
        outline=outline,
        warnings=[*competitor.warnings, *outline_agent.warnings],
    )
