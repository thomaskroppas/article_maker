"""
Параметры пайплайна: лимиты итераций, статусы, шаги, retry.
"""

# ─── Шаги пайплайна (в порядке выполнения) ───────────────────────────────────
PIPELINE_STEPS = [
    "input_validation",
    "serp_analysis",
    "competitor_analysis",
    "brief_generation",
    "outline_generation",
    "section_pipeline",
    "full_draft_assembly",
    "final_qa",
    "metadata_generation",
    "save_results",
]

# ─── Статусы статьи ───────────────────────────────────────────────────────────
STATUS_CREATED             = "created"
STATUS_INPUT_VALIDATED     = "input_validated"
STATUS_SERP_DONE           = "serp_analysis_done"
STATUS_COMPETITOR_DONE     = "competitor_analysis_done"
STATUS_BRIEF_DONE          = "brief_generated"
STATUS_OUTLINE_DONE        = "outline_generated"
STATUS_SECTIONS_PROGRESS   = "sections_in_progress"
STATUS_DRAFT_READY         = "draft_ready"
STATUS_QA_DONE             = "qa_done"
STATUS_COMPLETED           = "completed"
STATUS_FAILED              = "failed"
STATUS_STOPPED             = "stopped_by_user"

# Финальные статусы для GUI
FINAL_STATUS_READY         = "ready_for_manual_review"
FINAL_STATUS_READY_WARN    = "ready_for_manual_review_with_warnings"
FINAL_STATUS_FAILED        = "failed"

# ─── Лимиты ───────────────────────────────────────────────────────────────────
MAX_SECTION_ITERATIONS     = 3      # максимум циклов writer→critic→editor на секцию
MAX_RETRY_ATTEMPTS         = 5      # retry для LLM-вызовов
RETRY_DELAY_SECONDS        = 5      # базовая задержка между retry
PIPELINE_TIMEOUT_MINUTES   = 30     # таймаут всего пайплайна

# ─── Контроль длины секций ────────────────────────────────────────────────────
SECTION_WORD_COUNT_TOLERANCE = 0.20  # ±20% от target_word_count

# ─── SERP ─────────────────────────────────────────────────────────────────────
SERP_MIN_PAGES             = 3      # минимум страниц после фильтрации
SERP_MAX_PAGES             = 10     # максимум страниц
SERP_MAX_CONTENT_WORDS     = 8000   # обрезать контент страницы до N слов
SERP_WORKERS               = 5      # потоков для параллельной загрузки

# ─── QA пороги ────────────────────────────────────────────────────────────────
QA_SCORE_PASS              = 85     # ≥85 → pass
QA_SCORE_WARN              = 75     # 75–84 → pass_with_warnings
                                    # <75 → fail
