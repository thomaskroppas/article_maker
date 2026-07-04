"""critic_agent — оценка секции, ТЗ §7.3.6 (CriticFeedback §13.5)."""

from __future__ import annotations

from ..schemas import CriticFeedback
from .base import BaseAgent


class CriticAgent(BaseAgent):
    agent_name = "critic_agent"

    def run(self, brief, spec, section_text: str) -> CriticFeedback:
        resp = self._call(
            {
                "main_keyword": brief.keywords.main,
                "tone": brief.tone,
                "forbidden_words": ", ".join(brief.forbidden_words),
                "section_draft": section_text,
                "section_purpose": spec.purpose,
                "section_target_words": str(spec.target_word_count),
                "section_keywords": ", ".join(spec.keywords),
                "section_must_cover": ", ".join(spec.must_cover),
            }
        )
        return CriticFeedback.model_validate(self._parse_json(resp.text))
