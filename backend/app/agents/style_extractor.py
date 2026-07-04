"""style_extractor_agent — извлечение стиля референса (ТЗ §7.3, каталог авторов)."""

from __future__ import annotations

from .base import BaseAgent


class StyleExtractorAgent(BaseAgent):
    agent_name = "style_extractor_agent"

    def run(self, *, writer_name: str, language: str, geo: str, notes: str = "") -> dict:
        resp = self._call(
            {"writer_name": writer_name, "language": language, "geo": geo, "notes": notes}
        )
        data = self._parse_json(resp.text)
        if not isinstance(data, dict):
            data = {}
        return {
            "extracted_style": data.get("extracted_style", ""),
            "extracted_tone": data.get("extracted_tone", ""),
            "extracted_age_image": data.get("extracted_age_image", ""),
        }
