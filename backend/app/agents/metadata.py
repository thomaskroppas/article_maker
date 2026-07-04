"""metadata_agent — шаг 13 (ТЗ §6.16, §7.3.14): FinalPackage для публикации."""

from __future__ import annotations

import re

from ..schemas import FinalPackage
from .base import BaseAgent


def _slugify(title: str) -> str:
    s = re.sub(r"[^\wа-яёА-ЯЁ]+", "-", title.lower()).strip("-")
    return s[:80] or "article"


class MetadataAgent(BaseAgent):
    agent_name = "metadata_agent"

    def run(self, article_input, full_draft, qa_result) -> FinalPackage:
        ai = article_input
        resp = self._call(
            {
                "article_title": ai.article_title,
                "main_keyword": ai.main_keyword,
                "secondary_keywords": ", ".join(ai.secondary_keywords),
                "geo": ai.geo,
                "language": ai.language,
                "full_draft": full_draft.content_markdown,
                "qa_score": str(qa_result.score),
                "qa_status": qa_result.status,
                "qa_warnings": "; ".join(qa_result.warnings.critical + qa_result.warnings.medium),
            }
        )
        data = self._parse_json(resp.text)
        if not isinstance(data, dict):
            data = {}

        # Авторитетно из кода (не из LLM): id статьи и её итоговый markdown.
        data["article_id"] = ai.article_id
        data["article_markdown"] = full_draft.content_markdown
        # Остальное добираем, если LLM не вернул.
        data.setdefault("slug", _slugify(data.get("meta_title") or ai.article_title))
        data.setdefault("meta_title", ai.article_title[:60])
        data.setdefault("meta_description", "")
        data.setdefault("faq", [])
        data.setdefault("schema_data", {"type": "FAQPage", "data": {}})
        data.setdefault("category", "")
        data.setdefault("tags", [])
        data.setdefault("internal_links_suggestions", [])
        return FinalPackage.model_validate(data)
