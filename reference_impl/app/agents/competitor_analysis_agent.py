import json
import logging
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.serp_bundle import SerpBundle
from app.schemas.competitor_analysis_report import (
    CompetitorAnalysisReport, WordCountRange, H2CountRange,
    CommonH2Title, ContentGap, DataSensitivity
)

logger = logging.getLogger(__name__)


class CompetitorAnalysisAgent(BaseAgent):
    agent_name = "competitor_analysis_agent"

    def run(self, article_input: ArticleInput,
            serp_bundle: SerpBundle) -> CompetitorAnalysisReport:

        # Ограничиваем объём контента чтобы не обрезать JSON-ответ
        # 1500 слов на страницу × 8 страниц
        MAX_WORDS_PER_PAGE = 1500
        trimmed_parts = []
        for i, page in enumerate(serp_bundle.pages, 1):
            words = page.content.split()
            trimmed = ' '.join(words[:MAX_WORDS_PER_PAGE])
            part = '--- САЙТ ' + str(i) + ' ---\nURL: ' + page.url + '\n\n' + trimmed + '\n'
            trimmed_parts.append(part)
        trimmed_contents = '\n'.join(trimmed_parts)

        variables = {
            "main_keyword":  article_input.main_keyword,
            "analysis_csv":  serp_bundle.analysis_csv,
            "contents_txt":  trimmed_contents,
        }

        resp = self._call(variables)
        data = self._parse_json(resp.text)

        try:
            wc  = data.get("word_count_range", {})
            h2  = data.get("h2_count_range", {})
            ds  = data.get("data_sensitivity", {})

            # Парсим common_h2_titles
            common_h2 = []
            for t in data.get("common_h2_titles", []):
                if isinstance(t, dict):
                    common_h2.append(CommonH2Title(
                        title     = t.get("title", ""),
                        frequency = int(t.get("frequency", 0)),
                    ))

            # Парсим content_gaps — теперь объекты, не строки
            content_gaps = []
            for g in data.get("content_gaps", []):
                if isinstance(g, dict):
                    content_gaps.append(ContentGap(
                        title         = g.get("title", ""),
                        description   = g.get("description", ""),
                        after_section = g.get("after_section", "в конец"),
                        word_count    = int(g.get("word_count", 200)),
                    ))
                elif isinstance(g, str):
                    content_gaps.append(ContentGap(title=g))

            return CompetitorAnalysisReport(
                search_intent      = data.get("search_intent", "informational"),
                content_type       = data.get("content_type", "guide"),
                content_format     = data.get("content_format", "long_read"),
                word_count_range   = WordCountRange(**wc) if wc else WordCountRange(),
                h2_count_range     = H2CountRange(**h2) if h2 else H2CountRange(),
                common_h2_titles   = common_h2,
                structure_patterns = data.get("structure_patterns", []),
                common_sections    = data.get("common_sections", []),
                must_have_topics   = data.get("must_have_topics", []),
                optional_topics    = data.get("optional_topics", []),
                content_gaps       = content_gaps,
                tone               = data.get("tone", "neutral_informational"),
                target_audience    = data.get("target_audience", ""),
                data_sensitivity   = DataSensitivity(**ds) if ds else DataSensitivity(),
                raw_report         = data.get("raw_report", resp.text),
            )
        except Exception as e:
            raise ValueError(f"[competitor_analysis_agent] Ошибка сборки схемы: {e}\n{data}")
