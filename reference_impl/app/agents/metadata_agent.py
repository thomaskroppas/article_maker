import logging
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.brief import Brief
from app.schemas.output_schemas import FullDraft, QAResult, FinalPackage, FaqItem, SchemaBlock

logger = logging.getLogger(__name__)


class MetadataAgent(BaseAgent):
    agent_name = "metadata_agent"

    def run(self,
            article_input: ArticleInput,
            brief: Brief,
            full_draft: FullDraft,
            qa_result: QAResult) -> FinalPackage:

        variables = {
            "article_title":      article_input.article_title,
            "main_keyword":       article_input.main_keyword,
            "secondary_keywords": ", ".join(article_input.secondary_keywords),
            "language":           article_input.language,
            "geo":                article_input.geo,
            "qa_status":          qa_result.status,
            "qa_score":           qa_result.score,
            "qa_warnings":        "\n".join(f"- {w}" for w in qa_result.warnings) or "нет",
            "full_draft":         full_draft.content_markdown,
        }

        resp = self._call(variables)
        data = self._parse_json(resp.text)

        # FAQ
        faq_items = []
        for item in data.get("faq", []):
            if isinstance(item, dict):
                faq_items.append(FaqItem(
                    question = item.get("question", ""),
                    answer   = item.get("answer", ""),
                ))

        # Schema
        schema_raw = data.get("schema", {})
        schema = SchemaBlock(
            type = schema_raw.get("type", "FAQPage"),
            data = schema_raw.get("data", {}),
        )

        return FinalPackage(
            slug             = data.get("slug", ""),
            meta_title       = data.get("meta_title", ""),
            meta_description = data.get("meta_description", ""),
            article_markdown = full_draft.content_markdown,   # берём из draft, не меняем
            faq              = faq_items,
            schema           = schema,
            category         = data.get("category", ""),
            tags             = data.get("tags", []),
            internal_links_suggestions = data.get("internal_links_suggestions", []),
        )
