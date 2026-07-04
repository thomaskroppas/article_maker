import json
import logging
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.competitor_analysis_report import CompetitorAnalysisReport
from app.schemas.brief import Brief, KeywordsBlock, WordCountRange, DataHandlingRules

logger = logging.getLogger(__name__)


_LENGTH_MULTIPLIERS = {
    "shorter_top": 0.7,
    "match_top":   1.0,
    "longer_top":  1.3,
}
_FALLBACK_TARGET = 1200  # если нет данных о конкурентах и юзер не задал custom


def _compute_target_word_count(article_input: ArticleInput,
                               competitor_report: CompetitorAnalysisReport) -> int:
    """
    Вычисляет целевую длину статьи на основе стратегии.
    - custom: берём число указанное юзером.
    - shorter_top/match_top/longer_top: множитель * avg конкурентов.
    - Fallback если данных о конкурентах нет: 1200 слов.
    """
    strategy = getattr(article_input, "length_strategy", "match_top")

    if strategy == "custom":
        # Юзер сам указал цифру
        if article_input.target_word_count:
            return article_input.target_word_count
        logger.warning("[brief] custom без target_word_count — fallback на 1200")
        return _FALLBACK_TARGET

    avg = competitor_report.word_count_range.avg or 0
    if avg <= 0:
        # Нет данных о конкурентах — юзерский target как ориентир, иначе fallback
        return article_input.target_word_count or _FALLBACK_TARGET

    multiplier = _LENGTH_MULTIPLIERS.get(strategy, 1.0)
    return round(avg * multiplier)


class BriefAgent(BaseAgent):
    agent_name = "brief_agent"

    def run(self, article_input: ArticleInput,
            competitor_report: CompetitorAnalysisReport) -> Brief:

        variables = {
            "article_title":       article_input.article_title,
            "main_keyword":        article_input.main_keyword,
            "secondary_keywords":  ", ".join(article_input.secondary_keywords),
            "target_word_count":   _compute_target_word_count(article_input, competitor_report),
            "language":            article_input.language,
            "geo":                 article_input.geo,
            "intent":              article_input.intent,
            "article_type":        article_input.article_type,
            "difficulty":          article_input.difficulty,
            "style_archetype":     article_input.style_archetype,
            "forbidden_words":     ", ".join(article_input.forbidden_words),
            "required_elements":   ", ".join(article_input.required_elements),
            "optional_notes":      article_input.optional_notes or "",
            # Передаём только нужные поля — без raw_report
            "competitor_analysis_json": json.dumps({
                "search_intent":    competitor_report.search_intent,
                "content_type":     competitor_report.content_type,
                "word_count_range": competitor_report.word_count_range.model_dump(),
                "must_have_topics": competitor_report.must_have_topics,
                "optional_topics":  competitor_report.optional_topics,
                "content_gaps":     [g.model_dump() if hasattr(g, 'model_dump') else g
                                     for g in competitor_report.content_gaps],
                "tone":             competitor_report.tone,
                "target_audience":  competitor_report.target_audience,
                "data_sensitivity": competitor_report.data_sensitivity.model_dump(),
            }, ensure_ascii=False, indent=2),
        }

        resp = self._call(variables)
        data = self._parse_json(resp.text)

        try:
            kw  = data.get("keywords", {})
            wcr = data.get("word_count_range", {})
            dhr = data.get("data_handling_rules", {})
            return Brief(
                goal               = data.get("goal", ""),
                search_intent      = data.get("search_intent", "informational"),
                target_audience    = data.get("target_audience", ""),
                content_archetype  = data.get("content_archetype", "guide"),
                tone               = data.get("tone", "neutral_informational"),
                style_requirements = data.get("style_requirements", []),
                must_cover         = data.get("must_cover", []),
                must_not_cover     = data.get("must_not_cover", []),
                structure_guidelines = data.get("structure_guidelines", []),
                word_count_target  = data.get("word_count_target") or _compute_target_word_count(article_input, competitor_report),
                word_count_range   = WordCountRange(**wcr) if wcr else WordCountRange(),
                keywords           = KeywordsBlock(**kw) if kw else KeywordsBlock(),
                required_elements  = data.get("required_elements", article_input.required_elements),
                forbidden_words    = data.get("forbidden_words", article_input.forbidden_words),
                data_handling_rules = DataHandlingRules(**dhr) if dhr else DataHandlingRules(),
                raw_brief          = data.get("raw_brief", resp.text),
            )
        except Exception as e:
            raise ValueError(f"[brief_agent] Ошибка сборки схемы: {e}\n{data}")
