"""Цикл секции Writer → Critic → Editor — ТЗ §6.9.

Порог принятия CRITIC_PASS_SCORE (60), максимум SECTION_MAX_ITERATIONS (3).
enable_section_critic=False — секция принимается после первого прохода Writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..constants import CRITIC_PASS_SCORE, SECTION_MAX_ITERATIONS
from .critic import CriticAgent
from .editor import EditorAgent
from .text_utils import count_words, extract_summary
from .writer import WriterAgent

_SKIP_CRITIC = ("источник", "source", "литератур")


def _skip_critic(spec) -> bool:
    blob = f"{spec.section_id} {spec.title}".lower()
    return any(kw in blob for kw in _SKIP_CRITIC)


@dataclass
class SectionResult:
    section_id: str
    final_text: str  # без маркера SUMMARY
    summary: str
    iterations: int
    word_count: int
    is_weak: bool = False


def run_section(
    spec,
    article_input,
    brief,
    report,
    previous_summaries: list[str],
    writer: WriterAgent,
    critic: CriticAgent,
    editor: EditorAgent,
    *,
    enable_critic: bool = True,
    author: Optional[dict] = None,
) -> SectionResult:
    raw = writer.run(article_input, brief, spec, report, previous_summaries, author=author)
    text, summary = extract_summary(raw)
    iterations = 1
    is_weak = False

    if enable_critic and not _skip_critic(spec):
        while True:
            feedback = critic.run(brief, spec, text)
            if feedback.overall_score >= CRITIC_PASS_SCORE:
                break
            if iterations >= SECTION_MAX_ITERATIONS:
                is_weak = True
                break
            edited = editor.run(article_input, brief, spec, text, feedback)
            text, s2 = extract_summary(edited)
            if s2:
                summary = s2
            iterations += 1

    text = text.strip()
    return SectionResult(
        section_id=spec.section_id,
        final_text=text,
        summary=summary,
        iterations=iterations,
        word_count=count_words(text),
        is_weak=is_weak,
    )
