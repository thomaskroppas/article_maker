"""
Подбор архетипа статьи через LLM.
Дешёвый агент на Claude Haiku — небольшой промпт, маленький ответ.
"""
import logging
from typing import List, Optional, Dict

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ArchetypePickerAgent(BaseAgent):
    agent_name = "archetype_picker_agent"

    def run(self,
            topic: str,
            intent: str,
            archetypes: List[Dict]) -> Optional[str]:
        """
        Возвращает archetype_id, выбранный LLM. None если что-то пошло не так
        (вызывающий код должен сделать fallback на регэкспы).

        archetypes — список dict'ов с полями archetype_id, name_ru, description
        (то, что возвращает get_archetypes_for_niche).
        """
        if not archetypes:
            return None

        # Формируем список архетипов для промпта
        lines = []
        valid_ids = set()
        for a in archetypes:
            aid = a["archetype_id"]
            name = a.get("name_ru", aid)
            desc = a.get("description") or ""
            lines.append(f"- {aid} — {name}: {desc}")
            valid_ids.add(aid)
        archetypes_list = "\n".join(lines)

        variables = {
            "topic":           topic or "",
            "intent":          intent or "informational",
            "archetypes_list": archetypes_list,
        }

        try:
            resp = self._call(variables)
            data = self._parse_json(resp.text)
        except Exception as e:
            logger.warning(f"[archetype_picker] LLM call failed: {e}")
            return None

        chosen = data.get("archetype_id") if isinstance(data, dict) else None
        reason = data.get("reason") if isinstance(data, dict) else None

        # Защита: модель должна вернуть один из валидных id
        if chosen not in valid_ids:
            logger.warning(
                f"[archetype_picker] LLM вернул невалидный id: {chosen!r} "
                f"(допустимые: {sorted(valid_ids)})"
            )
            return None

        if reason:
            logger.info(f"[archetype_picker] выбран {chosen}: {reason}")
        return chosen
