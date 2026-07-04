import json
import logging
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.competitor_analysis_report import CompetitorAnalysisReport
from app.schemas.brief import Brief
from app.schemas.outline import Outline, SectionSpec, FaqSection

logger = logging.getLogger(__name__)


class OutlineAgent(BaseAgent):
    agent_name = "outline_agent"

    def run(self, article_input: ArticleInput,
            competitor_report: CompetitorAnalysisReport,
            brief: Brief) -> Outline:

        variables = {
            "main_keyword":          article_input.main_keyword,
            "target_word_count":     brief.word_count_target,
            "required_elements":     ", ".join(brief.required_elements),
            "brief_json":            json.dumps(brief.to_dict(), ensure_ascii=False, indent=2),
            # Передаём только структурные данные
            "competitor_analysis_json": json.dumps({
                "common_sections":   competitor_report.common_sections,
                "must_have_topics":  competitor_report.must_have_topics,
                "content_gaps":      [g.model_dump() if hasattr(g, 'model_dump') else g
                                      for g in competitor_report.content_gaps],
                "structure_patterns": competitor_report.structure_patterns,
                "word_count_range":  competitor_report.word_count_range.model_dump(),
            }, ensure_ascii=False, indent=2),
        }

        resp = self._call(variables)
        data = self._parse_json(resp.text)

        try:
            sections = []
            for i, s in enumerate(data.get("sections", [])):
                raw_level = s.get("level", "H2")
                level = raw_level if raw_level in ("H2", "H3") else "H2"

                sections.append(SectionSpec(
                    section_id        = s.get("section_id", f"s{i+1}"),
                    title             = s.get("title", ""),
                    level             = level,
                    purpose           = s.get("purpose", ""),
                    target_word_count = s.get("target_word_count", 200),
                    keywords          = s.get("keywords", []),
                    must_cover        = s.get("must_cover", []),
                ))

            faq_raw = data.get("faq_section", {})
            # Claude иногда возвращает вопросы как объекты {question: ..., purpose: ...}
            # вместо простых строк — нормализуем
            raw_questions = faq_raw.get("questions", [])
            questions = []
            for q in raw_questions:
                if isinstance(q, dict):
                    questions.append(q.get("question", ""))
                elif isinstance(q, str):
                    questions.append(q)
            questions = [q for q in questions if q]  # убираем пустые

            faq = FaqSection(
                enabled   = faq_raw.get("enabled", False),
                questions = questions,
            )

            return Outline(
                h1       = data.get("h1", article_input.article_title),
                sections = sections,
                faq_section = faq,
            )
        except Exception as e:
            raise ValueError(f"[outline_agent] Ошибка сборки схемы: {e}\n{data}")
