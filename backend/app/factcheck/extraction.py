"""fact_checker_agent (extraction) — ТЗ §9.4.1, §7.3.10.

LLM извлекает 5-20 атомарных FactStatement. Верификация — в verify.py (код).
"""

from __future__ import annotations

from ..agents.base import BaseAgent
from ..constants import FACT_CHECK_MAX_STATEMENTS
from ..schemas import FactStatement


class FactExtractionAgent(BaseAgent):
    agent_name = "fact_checker_agent"

    def run(self, article_markdown: str, language: str) -> list[FactStatement]:
        resp = self._call(
            {"article_markdown": article_markdown, "language": language}
        )
        data = self._parse_json(resp.text)
        if isinstance(data, dict):
            raw = data.get("statements", [])
        elif isinstance(data, list):
            raw = data
        else:
            raw = []

        statements: list[FactStatement] = []
        for item in raw[:FACT_CHECK_MAX_STATEMENTS]:  # максимум 20 (§9.6)
            try:
                statements.append(FactStatement.model_validate(item))
            except Exception:  # noqa: BLE001 — пропускаем невалидные
                continue
        return statements
