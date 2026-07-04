import logging
from app.agents.base_agent import BaseAgent
from app.schemas.brief import Brief
from app.schemas.outline import SectionSpec
from app.schemas.section_schemas import SectionDraft, ReviewReport

logger = logging.getLogger(__name__)


def _normalize_list(items: list) -> list[str]:
    """
    Нормализует список замечаний — модель иногда возвращает
    объекты {type, severity, description} вместо строк.
    """
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Собираем читаемую строку из полей объекта
            parts = []
            if item.get("type"):
                parts.append(f"[{item['type']}]")
            if item.get("severity"):
                parts.append(f"({item['severity']})")
            # description или любое другое текстовое поле
            for key in ("description", "message", "text", "issue", "detail"):
                if item.get(key):
                    parts.append(str(item[key]))
                    break
            if parts:
                result.append(" ".join(parts))
    return result


class CriticAgent(BaseAgent):
    agent_name = "critic_agent"

    def run(self,
            brief: Brief,
            section_spec: SectionSpec,
            section_draft: SectionDraft) -> ReviewReport:

        variables = {
            "main_keyword":         brief.keywords.main,
            "tone":                 brief.tone,
            "forbidden_words":      ", ".join(brief.forbidden_words) or "нет",
            "section_purpose":      section_spec.purpose,
            "section_must_cover":   ", ".join(section_spec.must_cover) or "нет",
            "section_keywords":     ", ".join(section_spec.keywords) or "нет",
            "section_target_words": section_spec.target_word_count,
            "section_draft":        section_draft.content,
        }

        resp = self._call(variables)
        data = self._parse_json(resp.text)

        return ReviewReport(
            section_id       = section_spec.section_id,
            status           = data.get("status", "ok"),
            issues           = _normalize_list(data.get("issues", [])),
            fix_instructions = _normalize_list(data.get("fix_instructions", [])),
            iteration        = section_draft.iteration,
        )
