import logging
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.brief import Brief
from app.schemas.outline import SectionSpec
from app.schemas.section_schemas import SectionDraft, ReviewReport, PatchedSection
from app.services.word_count_service import count_words

logger = logging.getLogger(__name__)


class EditorAgent(BaseAgent):
    agent_name = "editor_agent"

    def run(self,
            article_input: ArticleInput,
            brief: Brief,
            section_spec: SectionSpec,
            section_draft: SectionDraft,
            review_report: ReviewReport,
            serp_urls: list = None) -> PatchedSection:  # serp_urls не используется в редакторе

        variables = {
            "main_keyword":        article_input.main_keyword,
            "tone":                brief.tone,
            "forbidden_words":     ", ".join(brief.forbidden_words) or "нет",
            "language":            article_input.language,
            "section_title":       section_spec.title,
            "section_level":       section_spec.level,
            "section_purpose":     section_spec.purpose,
            "section_keywords":    ", ".join(section_spec.keywords) or "нет",
            "section_target_words": section_spec.target_word_count,
            "section_draft":       section_draft.content,
            "review_issues":       "\n".join(f"- {i}" for i in review_report.issues),
            "fix_instructions":    "\n".join(f"- {i}" for i in review_report.fix_instructions),
        }

        resp = self._call(variables)
        text = resp.text.strip()
        wc   = count_words(text)

        return PatchedSection(
            section_id = section_spec.section_id,
            title      = section_spec.title,
            content    = text,
            word_count = wc,
            iteration  = section_draft.iteration,
        )
