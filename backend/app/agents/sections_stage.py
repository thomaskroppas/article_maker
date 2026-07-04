"""Стадия секций (шаг 6) + сборка (шаг 7) — ТЗ §6.9–6.10.

Прогоняет все секции outline через Writer→Critic→Editor, прокидывая SUMMARY
предыдущих секций, и собирает FullDraft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..schemas import FullDraft
from .critic import CriticAgent
from .editor import EditorAgent
from .markdown_builder import assemble_draft
from .section_pipeline import SectionResult, run_section
from .writer import WriterAgent


@dataclass
class SectionsStageResult:
    draft: FullDraft
    section_results: list[SectionResult] = field(default_factory=list)
    weak_sections: list[str] = field(default_factory=list)


def run_sections_stage(
    article_input,
    brief,
    report,
    outline,
    llm,
    *,
    author: Optional[dict] = None,
) -> SectionsStageResult:
    writer, critic, editor = WriterAgent(llm), CriticAgent(llm), EditorAgent(llm)
    final_sections: dict[str, str] = {}
    previous_summaries: list[str] = []
    results: list[SectionResult] = []

    for spec in outline.sections:
        res = run_section(
            spec,
            article_input,
            brief,
            report,
            previous_summaries,
            writer,
            critic,
            editor,
            enable_critic=article_input.enable_section_critic,
            author=author,
        )
        final_sections[spec.section_id] = res.final_text
        results.append(res)
        if res.summary:
            previous_summaries.append(f"{spec.title}: {res.summary}")

    draft = assemble_draft(outline, final_sections)
    return SectionsStageResult(
        draft=draft,
        section_results=results,
        weak_sections=[r.section_id for r in results if r.is_weak],
    )
