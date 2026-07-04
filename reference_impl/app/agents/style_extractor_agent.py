"""
Извлекает стилистические маркеры писателя-референса.
Дешёвый агент на Haiku. Результат кэшируется в БД (style_references.extracted_style).
"""
import json
import logging
from typing import Optional, Dict

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class StyleExtractorAgent(BaseAgent):
    agent_name = "style_extractor_agent"

    def run(self, reference: Dict) -> Optional[Dict]:
        """
        reference — dict из style_references (name, language, geo, notes).
        Возвращает dict с character/tone/age_image или None при ошибке.
        """
        variables = {
            "writer_name": reference.get("name", ""),
            "language":    reference.get("language", "ru"),
            "geo":         reference.get("geo", "RU"),
            "notes":       reference.get("notes") or "—",
        }
        try:
            resp = self._call(variables)
            data = self._parse_json(resp.text)
        except Exception as e:
            logger.warning(f"[style_extractor] LLM call failed: {e}")
            return None

        if not isinstance(data, dict):
            return None

        # Минимально валидируем
        character = data.get("character")
        if not character or len(character) < 30:
            logger.warning(f"[style_extractor] невалидный character: {character!r}")
            return None

        return {
            "character": character.strip(),
            "tone":      (data.get("tone") or "").strip(),
            "age_image": (data.get("age_image") or "").strip(),
        }