import logging
from typing import Dict, List
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.brief import Brief
from app.schemas.outline import SectionSpec
from app.schemas.competitor_analysis_report import CompetitorAnalysisReport
from app.schemas.section_schemas import SectionDraft
from app.services.word_count_service import count_words

logger = logging.getLogger(__name__)

_SOURCES_KEYWORDS = ("источник", "source", "литератур", "ссылк", "список использ")


def _is_sources_section(spec: SectionSpec) -> bool:
    text = (spec.title + " " + spec.section_id).lower()
    return any(kw in text for kw in _SOURCES_KEYWORDS)


class WriterAgent(BaseAgent):
    agent_name = "writer_agent"

    def run(self,
            article_input: ArticleInput,
            brief: Brief,
            section_spec: SectionSpec,
            competitor_report: CompetitorAnalysisReport,
            previous_sections: Dict[str, str],
            iteration: int = 1,
            serp_urls: List[str] = None,
            manual_sources: List[str] = None,
            author: dict = None) -> SectionDraft:

        prev_summary = "\n".join(
            f"- {sid}" for sid in previous_sections.keys()
        ) or "Это первая секция."

        sources_hint = ""
        if _is_sources_section(section_spec):
            if manual_sources:
                # Вариант 4: используем источники из JSON краулера
                urls_block = "\n".join(f"- {s}" for s in manual_sources)
                sources_hint = (
                    f"\n\nВАЖНО: Это секция источников. "
                    f"Используй ТОЛЬКО эти предоставленные ссылки:\n{urls_block}\n"
                    f"Оформи их как нумерованный список в Markdown. "
                    f"Не добавляй другие источники от себя."
                )
            else:
                # Вариант 2: Gemini пишет из своих знаний
                sources_hint = (
                    f"\n\nВАЖНО: Это секция источников по теме '{article_input.article_title}'. "
                    f"Напиши список из 5-7 авторитетных источников которые реально существуют: "
                    f"официальные сайты, Википедия, научные организации, государственные ресурсы. "
                    f"Используй только те источники в которых уверен. "
                    f"Формат: нумерованный список с названием и полным URL."
                )

        author_block = _format_author_block(author)

        variables = {
            "author_block":         author_block,
            "article_title":        article_input.article_title,
            "main_keyword":         article_input.main_keyword,
            "lsi_keywords":         ", ".join(brief.lsi_keywords) or "—",
            "style_archetype":      article_input.style_archetype,
            "tone":                 brief.tone,
            "forbidden_words":      ", ".join(brief.forbidden_words) or "нет",
            "language":             article_input.language,
            "brief_summary":        brief.goal + sources_hint,
            "previous_sections":    prev_summary,
            "section_id":           section_spec.section_id,
            "section_title":        section_spec.title,
            "section_level":        section_spec.level,
            "section_purpose":      section_spec.purpose,
            "section_keywords":     ", ".join(section_spec.keywords) or "нет",
            "section_must_cover":   ", ".join(section_spec.must_cover) or "нет",
            "section_target_words": section_spec.target_word_count,
            "competitor_analysis_summary": (
                f"Обязательные темы: {', '.join(competitor_report.must_have_topics)}\n"
                f"Аудитория: {competitor_report.target_audience}\n"
                f"Средний объём конкурентов: {int(competitor_report.word_count_range.avg)} слов"
            ),
        }

        resp = self._call(variables)
        text = resp.text.strip()
        wc   = count_words(text)

        return SectionDraft(
            section_id = section_spec.section_id,
            title      = section_spec.title,
            content    = text,
            word_count = wc,
            iteration  = iteration,
        )
    
def _format_author_block(author: dict) -> str:
    """Форматирует блок автора для промпта. Если автора нет — нейтральный текст."""
    if not author:
        return "Автор не задан — пиши нейтральным редакторским голосом."
    parts = []
    name = author.get("name")
    age  = author.get("age_image")
    if name:
        head = f"Тебя зовут {name}"
        if age:
            head += f", {age}"
        parts.append(head + ".")
    tone = author.get("tone")
    if tone:
        parts.append(f"Твой тон: {tone}.")
    character = author.get("character")
    if character:
        parts.append(f"Твой характер и манера: {character}")
    parts.append("Выдерживай этот голос во всём тексте секции.")
    return "\n".join(parts)
