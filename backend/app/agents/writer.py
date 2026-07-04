"""writer_agent — шаг 6 (написание секции), ТЗ §7.3.5."""

from __future__ import annotations

from typing import Optional

from .base import BaseAgent


def _author_block(author: Optional[dict]) -> str:
    if not author:
        return ""
    return (
        f"Имя: {author.get('name', '')}\n"
        f"Характер: {author.get('character', '')}\n"
        f"Тон: {author.get('tone', '')}\n"
        f"Возрастной образ: {author.get('age_image', '')}"
    )


class WriterAgent(BaseAgent):
    agent_name = "writer_agent"

    def run(
        self,
        article_input,
        brief,
        spec,
        report,
        previous_summaries: list[str],
        *,
        author: Optional[dict] = None,
    ) -> str:
        ai = article_input
        resp = self._call(
            {
                "article_title": ai.article_title,
                "main_keyword": ai.main_keyword,
                "language": ai.language,
                "style_archetype": ai.style_archetype,
                "tone": brief.tone,
                "forbidden_words": ", ".join(brief.forbidden_words),
                "lsi_keywords": ", ".join(brief.lsi_keywords),
                "brief_summary": brief.goal,
                "competitor_analysis_summary": ", ".join(report.must_have_topics),
                "author_block": _author_block(author),
                "previous_sections": "\n".join(previous_summaries),
                "section_id": spec.section_id,
                "section_title": spec.title,
                "section_level": spec.level,
                "section_purpose": spec.purpose,
                "section_target_words": str(spec.target_word_count),
                "section_keywords": ", ".join(spec.keywords),
                "section_must_cover": ", ".join(spec.must_cover),
            }
        )
        return resp.text
