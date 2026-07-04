"""
section_pipeline — цикл write → (self-check или critic) → edit для одной секции.

always_review=True  → всегда запускать Critic после Writer (качественнее, дороже)
always_review=False → Writer делает self-check; Critic только если есть проблемы
"""
import logging
from typing import Dict, Callable, Optional

from app.agents.writer_agent import WriterAgent
from app.agents.critic_agent import CriticAgent
from app.agents.editor_agent import EditorAgent
from app.schemas.article_input import ArticleInput
from app.schemas.brief import Brief
from app.schemas.outline import SectionSpec
from app.schemas.competitor_analysis_report import CompetitorAnalysisReport
from app.schemas.section_schemas import SectionDraft, ReviewReport
from app.storage.artifact_manager import ArtifactManager
from app.config.pipeline_settings import MAX_SECTION_ITERATIONS

logger = logging.getLogger(__name__)


class SectionResult:
    def __init__(self, section_id: str, final_text: str,
                 iterations: int, word_count: int,
                 is_weak: bool = False, summary: str = ""):
        self.section_id = section_id
        self.final_text = final_text
        self.iterations = iterations
        self.word_count = word_count
        self.is_weak    = is_weak
        self.summary    = summary


def _self_check(draft: SectionDraft, spec: SectionSpec,
                brief: Brief) -> ReviewReport:
    """
    Быстрая самопроверка без LLM.
    Проверяет длину и наличие запрещённых слов.
    Если всё ок — возвращает status='ok' и Critic не вызывается.
    """
    issues = []
    fix_instructions = []
    wc = draft.word_count
    target = spec.target_word_count
    tolerance = 0.20

    if target > 0:
        deviation = abs(wc - target) / target
        if deviation > tolerance:
            issues.append(f"Длина секции {wc} слов, ожидается {target} (±20%)")
            fix_instructions.append(
                f"{'Увеличь' if wc < target else 'Сократи'} текст до ~{target} слов"
            )

    for word in brief.forbidden_words:
        if word.lower() in draft.content.lower():
            issues.append(f"Запрещённое слово/фраза: '{word}'")
            fix_instructions.append(f"Убери фразу '{word}' из текста")

    return ReviewReport(
        section_id       = spec.section_id,
        status           = "needs_revision" if issues else "ok",
        issues           = issues,
        fix_instructions = fix_instructions,
        iteration        = draft.iteration,
    )


def run_section(
    spec:              SectionSpec,
    article_input:     ArticleInput,
    brief:             Brief,
    competitor_report: CompetitorAnalysisReport,
    previous_sections: Dict[str, str],
    writer:            WriterAgent,
    critic:            CriticAgent,
    editor:            EditorAgent,
    artifact_mgr:      ArtifactManager,
    always_review:     bool = True,
    stop_flag:         Optional[Callable[[], bool]] = None,
    progress_cb:       Optional[Callable[[str], None]] = None,
    prompt_cb:         Optional[Callable[[str, str, str], None]] = None,
    serp_urls:         list = None,
    manual_sources:    list = None,
    author:            dict = None,
) -> SectionResult:

    sid = spec.section_id

    def progress(msg: str):
        logger.info(f"[{sid}] {msg}")
        if progress_cb:
            progress_cb(msg)

    def emit_prompt(agent_name: str, agent):
        if prompt_cb:
            prompt_cb(agent_name, agent.last_prompt, agent.last_response)

    # Секцию источников Critic не проверяет — там нет смысла
    _SKIP_CRITIC_IDS = ("источник", "source", "литератур")
    skip_critic = any(kw in spec.section_id.lower() or kw in spec.title.lower()
                      for kw in _SKIP_CRITIC_IDS)

    progress(f"Writer пишет '{spec.title}'...")
    draft = writer.run(
        article_input, brief, spec,
        competitor_report, previous_sections, iteration=1,
        serp_urls=serp_urls or [],
        manual_sources=manual_sources,
        author=author,
    )
    artifact_mgr.save_section(sid, "draft", draft.to_dict())
    artifact_mgr.save_prompt(f"section_{sid}_writer_1",
                              writer.last_prompt, writer.last_response)
    emit_prompt("writer_agent", writer)

    iterations = 0
    is_weak    = False

    while iterations < MAX_SECTION_ITERATIONS:
        if stop_flag and stop_flag():
            break

        if skip_critic:
            progress(f"Секция '{spec.title}' — источники, Critic пропускается ✓")
            break

        if always_review:
            # ── Режим: всегда Critic ───────────────────────────────────────
            progress(f"Critic проверяет '{spec.title}' (итерация {iterations+1})...")
            review = critic.run(brief, spec, draft)
            artifact_mgr.save_section(sid, f"review_{iterations+1}", review.to_dict())
            artifact_mgr.save_prompt(f"section_{sid}_critic_{iterations+1}",
                                      critic.last_prompt, critic.last_response)
            emit_prompt("critic_agent", critic)
        else:
            # ── Режим: self-check сначала ──────────────────────────────────
            progress(f"Self-check '{spec.title}'...")
            review = _self_check(draft, spec, brief)

            if review.needs_revision:
                # Есть базовые проблемы — зовём Critic
                progress(f"Self-check нашёл проблемы → Critic проверяет...")
                review = critic.run(brief, spec, draft)
                artifact_mgr.save_section(sid, f"review_{iterations+1}", review.to_dict())
                artifact_mgr.save_prompt(f"section_{sid}_critic_{iterations+1}",
                                          critic.last_prompt, critic.last_response)
                emit_prompt("critic_agent", critic)
            else:
                # Self-check пройден — пропускаем Critic
                progress(f"Self-check пройден ✓ (Critic пропущен)")
                artifact_mgr.save_section(sid, f"review_{iterations+1}", review.to_dict())

        if not review.needs_revision:
            progress(f"Секция '{spec.title}' финальная ✓")
            break

        iterations += 1
        if iterations >= MAX_SECTION_ITERATIONS:
            is_weak = True
            progress(f"⚠ Секция не прошла после {MAX_SECTION_ITERATIONS} итераций")
            break

        progress(f"Editor правит '{spec.title}'...")
        patched = editor.run(article_input, brief, spec, draft, review,
                             serp_urls=serp_urls or [])
        artifact_mgr.save_section(sid, f"patched_{iterations}", patched.to_dict())
        artifact_mgr.save_prompt(f"section_{sid}_editor_{iterations}",
                                  editor.last_prompt, editor.last_response)
        emit_prompt("editor_agent", editor)

        draft = SectionDraft(
            section_id = patched.section_id,
            title      = patched.title,
            content    = patched.content,
            word_count = patched.word_count,
            iteration  = iterations + 1,
        )

    artifact_mgr.save_section(sid, "final", {
        "section_id": sid,
        "title":      spec.title,
        "content":    draft.content,
        "word_count": draft.word_count,
        "iterations": iterations,
        "is_weak":    is_weak,
    })
    artifact_mgr.upsert_section(sid, "weak" if is_weak else "done",
                                 iterations, draft.word_count)

    # Вырезаем резюме из текста — оно в финальный markdown не попадёт.
    from app.utils.text_utils import extract_summary
    final_text, summary = extract_summary(draft.content)

    return SectionResult(
        section_id = sid,
        final_text = final_text,
        iterations = iterations,
        word_count = draft.word_count,
        is_weak    = is_weak,
        summary    = summary,
    )
