"""
LSI-агент. Извлекает тематически связанные слова из SERP-выжимки.
Шаг между competitor_analysis и brief.

Стоимость: ~$0.001-0.003 на Haiku. Кэшируется через agent_cache.
"""
import logging
from typing import List

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class LSIAgent(BaseAgent):
    agent_name = "lsi_agent"

    def run(self, article_input, competitor_report) -> List[str]:
        """
        Возвращает список LSI-слов (15-20 элементов). При ошибке — пустой список.
        """
        # Подготовка переменных для шаблона из реальных полей CompetitorAnalysisReport
        common_h2 = "\n".join(
            f"- {h.title} ({h.frequency} раз)"
            for h in (competitor_report.common_h2_titles or [])
        ) or "(нет данных)"

        must_have = "\n".join(
            f"- {t}" for t in (competitor_report.must_have_topics or [])
        ) or "(нет данных)"

        optional = "\n".join(
            f"- {t}" for t in (competitor_report.optional_topics or [])
        ) or "(нет данных)"

        content_gaps = "\n".join(
            f"- {g.title}: {g.description}"
            for g in (competitor_report.content_gaps or [])
        ) or "(нет данных)"

        variables = {
            "article_title":        article_input.article_title,
            "main_keyword":         article_input.main_keyword,
            "secondary_keywords":   ", ".join(article_input.secondary_keywords) or "—",
            "competitor_titles":    must_have,
            "common_h2":            common_h2,
            "content_gaps":         content_gaps + "\n" + optional,
        }

        try:
            resp = self._call(variables)
            data = self._parse_json(resp.text)
        except Exception as e:
            logger.warning(f"[lsi_agent] LLM-вызов упал: {e}")
            return []

        if not isinstance(data, list):
            logger.warning(f"[lsi_agent] невалидный формат ответа: {type(data)}")
            return []

        # Чистка: убираем пустые, дубли, очень длинные
        seen = set()
        result = []
        for item in data:
            s = str(item).strip()
            if not s or len(s) > 60:
                continue
            low = s.lower()
            if low in seen:
                continue
            seen.add(low)
            result.append(s)
            if len(result) >= 25:
                break

        logger.info(f"[lsi_agent] извлечено {len(result)} LSI-слов")
        return result
