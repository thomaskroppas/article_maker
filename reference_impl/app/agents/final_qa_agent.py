"""
FinalQAAgent — финальная оценка качества статьи.

Гибридная схема:
  - 5 критериев считаются детерминированно кодом (qa_metrics.py)
  - 3 критерия оценивает LLM (brief_alignment, intent_coverage, factuality)
  - Итоговый score = взвешенная сумма всех 8 критериев

Веса:
  brief_alignment  0.20
  completeness     0.20
  intent_coverage  0.15
  keyword_usage    0.15
  readability      0.10
  structure        0.10
  factuality       0.05
  length_control   0.05
"""
import logging
from app.agents.base_agent import BaseAgent
from app.schemas.article_input import ArticleInput
from app.schemas.brief import Brief
from app.schemas.competitor_analysis_report import CompetitorAnalysisReport
from app.schemas.output_schemas import FullDraft, QAResult, CriteriaScores
from app.config.pipeline_settings import QA_SCORE_PASS, QA_SCORE_WARN
from app.services.qa_metrics import calc_code_metrics

logger = logging.getLogger(__name__)

# ─── Веса критериев ───────────────────────────────────────────────────────────

WEIGHTS = {
    "brief_alignment":  0.20,
    "completeness":     0.20,
    "intent_coverage":  0.15,
    "keyword_usage":    0.10,
    "lsi_coverage":     0.05,
    "readability":      0.10,
    "structure":        0.10,
    "factuality":       0.05,
    "length_control":   0.05,
}


class FinalQAAgent(BaseAgent):
    agent_name = "final_qa_agent"

    def run(self,
            article_input: ArticleInput,
            brief: Brief,
            competitor_report: CompetitorAnalysisReport,
            full_draft: FullDraft) -> QAResult:

        text = full_draft.content_markdown

        # ── Шаг 1: детерминированные метрики (без LLM) ────────────────────────
        try:
            code_m = calc_code_metrics(
                text               = text,
                target_words       = brief.word_count_target,
                main_keyword       = article_input.main_keyword,
                secondary_keywords = article_input.secondary_keywords,
                required_elements  = brief.required_elements,
                lsi_keywords       = brief.lsi_keywords,
            )
            logger.info(
                f"[QA code metrics] "
                f"length={code_m.length_control} "
                f"completeness={code_m.completeness} "
                f"keywords={code_m.keyword_usage} "
                f"lsi={code_m.lsi_coverage} "
                f"structure={code_m.structure} "
                f"readability={code_m.readability}"
            )
        except Exception as e:
            logger.error(f"[QA] code metrics failed: {e}")
            return self._fallback_result(f"Ошибка расчёта метрик: {e}")

        # ── Шаг 2: LLM оценивает 3 субъективных критерия ─────────────────────
        try:
            variables = {
                "main_keyword":       article_input.main_keyword,
                "target_word_count":  brief.word_count_target,
                "required_elements":  ", ".join(brief.required_elements),
                "brief_summary": (
                    f"Цель: {brief.goal}\n"
                    f"Must-cover: {', '.join(brief.must_cover)}\n"
                    f"Must-not: {', '.join(brief.must_not_cover)}"
                ),
                "competitor_summary": (
                    f"Обязательные темы: {', '.join(competitor_report.must_have_topics)}\n"
                    f"Средний объём: {int(competitor_report.word_count_range.avg)} слов"
                ),
                "full_draft": text,
                "code_metrics_summary": (
                    f"Уже посчитано кодом:\n"
                    f"  Объём: {code_m.details['actual_words']} слов "
                    f"(отклонение {code_m.details['word_deviation_pct']}%)\n"
                    f"  Обязательные элементы: {code_m.details['completeness_map']}\n"
                    f"  Длинных предложений (>20 слов): {code_m.details['sentences_long_pct']}%\n"
                    f"  H2 заголовков: {code_m.details['h2_count']}"
                ),
            }
            resp = self._call(variables)
            data = self._parse_json(resp.text)
        except Exception as e:
            logger.error(f"[QA] LLM call failed: {e} — using code-only fallback")
            return self._code_only_result(code_m)

        # ── Шаг 3: собираем все 8 критериев ──────────────────────────────────
        try:
            llm_scores = data.get("criteria_scores", {})
            brief_alignment = float(llm_scores.get("brief_alignment", 0))
            intent_coverage = float(llm_scores.get("intent_coverage", 0))
            factuality      = float(llm_scores.get("factuality",      0))

            all_scores = {
                "brief_alignment":  brief_alignment,
                "completeness":     code_m.completeness,
                "intent_coverage":  intent_coverage,
                "keyword_usage":    code_m.keyword_usage,
                "lsi_coverage":     code_m.lsi_coverage,
                "readability":      code_m.readability,
                "structure":        code_m.structure,
                "factuality":       factuality,
                "length_control":   code_m.length_control,
            }

            score = sum(all_scores[c] * w for c, w in WEIGHTS.items())
            score = max(0, min(100, round(score)))

            if score >= QA_SCORE_PASS:
                status = "pass"
            elif score >= QA_SCORE_WARN:
                status = "pass_with_warnings"
            else:
                status = "fail"

            logger.info(
                f"[QA final] score={score} status={status} | "
                f"brief={brief_alignment:.0f} intent={intent_coverage:.0f} "
                f"factuality={factuality:.0f}"
            )

            criteria = CriteriaScores(
                brief_alignment = brief_alignment,
                intent_coverage = intent_coverage,
                keyword_usage   = code_m.keyword_usage,
                lsi_coverage    = code_m.lsi_coverage,
                factuality      = factuality,
                structure       = code_m.structure,
                readability     = code_m.readability,
                length_control  = code_m.length_control,
                completeness    = code_m.completeness,
            )

            warnings = list(data.get("warnings", []))
            self._add_code_warnings(warnings, code_m, all_scores)

            return QAResult(
                status          = status,
                score           = score,
                criteria_scores = criteria,
                warnings        = warnings,
                fail_reasons    = data.get("fail_reasons", []),
                recommendation  = data.get("recommendation", ""),
            )

        except Exception as e:
            logger.error(f"[QA] score assembly failed: {e} — using code-only fallback")
            return self._code_only_result(code_m)

    def _code_only_result(self, code_m) -> QAResult:
        """Fallback: считаем score только по кодовым метрикам (LLM недоступен).
        LLM-критерии получают нейтральное значение 70."""
        neutral = 70.0
        all_scores = {
            "brief_alignment":  neutral,
            "completeness":     code_m.completeness,
            "intent_coverage":  neutral,
            "keyword_usage":    code_m.keyword_usage,
            "lsi_coverage":     code_m.lsi_coverage,
            "readability":      code_m.readability,
            "structure":        code_m.structure,
            "factuality":       neutral,
            "length_control":   code_m.length_control,
        }
        score = max(0, min(100, round(
            sum(all_scores[c] * w for c, w in WEIGHTS.items())
        )))
        status = "pass" if score >= QA_SCORE_PASS else \
                 "pass_with_warnings" if score >= QA_SCORE_WARN else "fail"

        warnings = ["⚠ LLM-оценка недоступна — brief_alignment, intent_coverage, factuality выставлены нейтрально (70)"]
        self._add_code_warnings(warnings, code_m, all_scores)

        logger.warning(f"[QA] code-only fallback score={score}")
        return QAResult(
            status          = status,
            score           = score,
            criteria_scores = CriteriaScores(
                brief_alignment = neutral,
                intent_coverage = neutral,
                keyword_usage   = code_m.keyword_usage,
                lsi_coverage    = code_m.lsi_coverage,
                factuality      = neutral,
                structure       = code_m.structure,
                readability     = code_m.readability,
                length_control  = code_m.length_control,
                completeness    = code_m.completeness,
            ),
            warnings        = warnings,
            fail_reasons    = [],
            recommendation  = "Оценка выполнена без LLM — проверьте вручную соответствие ТЗ и интент.",
        )

    def _fallback_result(self, reason: str) -> QAResult:
        """Полный fallback когда даже кодовые метрики не посчитались."""
        logger.error(f"[QA] full fallback: {reason}")
        return QAResult(
            status          = "pass_with_warnings",
            score           = 0,
            criteria_scores = CriteriaScores(),
            warnings        = [f"⚠ QA не выполнен: {reason}"],
            fail_reasons    = [reason],
            recommendation  = "Проверьте статью вручную.",
        )

    def _add_code_warnings(self, warnings: list, code_m, scores: dict):
        """Добавляет автоматические предупреждения на основе кодовых метрик."""
        d = code_m.details

        if scores["length_control"] < 60:
            dev = d["word_deviation_pct"]
            actual = d["actual_words"]
            target = d["target_words"]
            direction = "меньше" if actual < target else "больше"
            warnings.append(
                f"Объём статьи ({actual} слов) на {dev}% {direction} целевого ({target} слов)"
            )

        if scores["completeness"] < 75:
            missing = [k for k, v in d["completeness_map"].items() if not v]
            if missing:
                warnings.append(f"Отсутствуют обязательные элементы: {', '.join(missing)}")

        if scores["readability"] < 60:
            warnings.append(
                f"Читаемость снижена: {d['sentences_long_pct']}% предложений "
                f"длиннее 20 слов"
            )

        if scores["structure"] < 60:
            warnings.append(
                f"Слабая структура: найдено H2 заголовков — {d['h2_count']} "
                f"(рекомендуется ≥3)"
            )

        if scores["keyword_usage"] < 50:
            warnings.append(
                "Низкое использование ключевых слов — проверьте плотность "
                "главного ключа и покрытие второстепенных"
            )
