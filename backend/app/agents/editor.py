"""editor_agent — правка секции по замечаниям критика, ТЗ §7.3.7."""

from __future__ import annotations

from ..schemas import CriticFeedback
from .base import BaseAgent


class EditorAgent(BaseAgent):
    agent_name = "editor_agent"

    def run(self, article_input, brief, spec, section_text: str, feedback: CriticFeedback) -> str:
        ai = article_input
        resp = self._call(
            {
                "main_keyword": ai.main_keyword,
                "language": ai.language,
                "tone": brief.tone,
                "forbidden_words": ", ".join(brief.forbidden_words),
                "section_draft": section_text,
                "section_title": spec.title,
                "section_level": spec.level,
                "section_purpose": spec.purpose,
                "section_target_words": str(spec.target_word_count),
                "section_keywords": ", ".join(spec.keywords),
                "review_issues": "; ".join(feedback.issues),
                "fix_instructions": "; ".join(feedback.suggestions),
            }
        )
        return resp.text
