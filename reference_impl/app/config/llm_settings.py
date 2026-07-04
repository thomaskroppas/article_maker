"""
Настройки LLM-моделей по агентам.

Принцип распределения — по задачам:
  - Все основные роли (анализ, brief, outline, writer, editor, critic, QA, metadata)
    → Claude Sonnet 4.6. Единая модель для качества и предсказуемости стиля.
  - Архетип-пикер (короткий запрос, JSON-ответ) → Claude Haiku 4.5 (дёшево).

Gemini-константы оставлены в коде на случай возврата к Gemini Pro/Flash для
writer/editor (если решится вопрос с региональной блокировкой 400) — переключение
требует только смены провайдера и модели у соответствующего агента.

Цены за 1 миллион токенов (на 8 июня 2026, источник — публичные прайс-листы):
  Claude Haiku 4.5:    $1.00 input / $5.00 output
  Claude Sonnet 4.6:   $3.00 input / $15.00 output
  Claude Opus 4.7:     $5.00 input / $25.00 output  (не используется)
  Claude Opus 4.8:     $5.00 input / $25.00 output  (не используется)
  Gemini 2.5 Pro:      $1.25 input / $10.00 output  (резерв)
  Gemini 2.5 Flash:    $0.15 input / $0.60 output   (резерв)
"""

# ─── Провайдеры ───────────────────────────────────────────────────────────────
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI    = "openai"
PROVIDER_GOOGLE    = "google"

# ─── Модели ───────────────────────────────────────────────────────────────────
# Claude
CLAUDE_SONNET_MODEL = "claude-sonnet-4-6"          # основная рабочая лошадка
CLAUDE_HAIKU_MODEL  = "claude-haiku-4-5-20251001"  # дешёвые короткие задачи (архетип-пикер)
CLAUDE_OPUS_MODEL   = "claude-opus-4-7"            # резерв на случай переезда сложных задач

# Gemini (резерв на случай возврата к Gemini для writer/editor)
GEMINI_PRO_MODEL   = "gemini-2.5-pro"
GEMINI_FLASH_MODEL = "gemini-2.5-flash"

# ─── Назначение моделей по агентам ───────────────────────────────────────────
AGENT_MODELS = {
    "competitor_analysis_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    "brief_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    "outline_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    "final_qa_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    "critic_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,   # Haiku слишком строгий — все секции проваливают
    },
    "metadata_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,   # Haiku обрезает JSON при большом full_draft
    },
    # Writer и editor — раньше были на Gemini Pro/Flash, переведены на Sonnet 4.6
    # из-за региональной блокировки Gemini (400 User location is not supported).
    # При желании вернуть Gemini — провайдер + модель меняются здесь же.
    "writer_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    "editor_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    # Подбор архетипа по теме → Haiku (дёшево, маленький запрос)
    "archetype_picker_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_HAIKU_MODEL,
    },
    # Извлечение стиля писателя-референса → Haiku (один вызов на референс,
    # результат кэшируется в БД)
    "style_extractor_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_HAIKU_MODEL,
    },
    # Подбор ключей для поиска картинок → Haiku (один вызов на статью,
    # результат кэшируется по main_keyword)
    "image_keys_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_HAIKU_MODEL,
    },
    # FAQ Writer — те же настройки что у обычного Writer'а (Sonnet,
    # важно для сохранения стиля автора)
    "faq_writer_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_SONNET_MODEL,
    },
    # Извлечение LSI-слов из SERP → Haiku
    "lsi_agent": {
        "provider": PROVIDER_ANTHROPIC,
        "model":    CLAUDE_HAIKU_MODEL,
    },
}

# ─── Параметры вызовов ────────────────────────────────────────────────────────
DEFAULT_MAX_TOKENS  = 8192
DEFAULT_TEMPERATURE = 0.7

AGENT_PARAMS = {
    "competitor_analysis_agent": {"max_tokens": 8192, "temperature": 0.3},
    "brief_agent":               {"max_tokens": 8192, "temperature": 0.4},
    "outline_agent":             {"max_tokens": 8192, "temperature": 0.3},
    "writer_agent":              {"max_tokens": 8192, "temperature": 0.7},
    "critic_agent":              {"max_tokens": 4096, "temperature": 0.2},
    "editor_agent":              {"max_tokens": 8192, "temperature": 0.6},
    "final_qa_agent":            {"max_tokens": 2048, "temperature": 0.2},
    "metadata_agent":            {"max_tokens": 4096, "temperature": 0.4},
    "archetype_picker_agent":    {"max_tokens": 512,  "temperature": 0.1},
    "style_extractor_agent":     {"max_tokens": 1500, "temperature": 0.3},
    "image_keys_agent":          {"max_tokens": 500,  "temperature": 0.3},
    "faq_writer_agent":          {"max_tokens": 2000, "temperature": 0.6},
    "lsi_agent":                 {"max_tokens": 800,  "temperature": 0.2},
}

# ─── Цены за 1 миллион токенов (USD, 8 июня 2026) ────────────────────────────
MODEL_PRICES = {
    # Claude (актуальное поколение)
    "claude-haiku-4-5-20251001":      {"input": 1.00,  "output": 5.00},
    "claude-sonnet-4-6":              {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":                {"input": 5.00,  "output": 25.00},
    "claude-opus-4-8":                {"input": 5.00,  "output": 25.00},
    # Claude (предыдущее поколение — оставлено для совместимости со старыми записями)
    "claude-sonnet-4-5":              {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":                {"input": 5.00,  "output": 25.00},
    # Gemini (резерв)
    "gemini-2.5-pro":                 {"input": 1.25,  "output": 10.00},
    "gemini-2.5-flash":               {"input": 0.15,  "output": 0.60},
    "gemini-2.5-flash-lite":          {"input": 0.10,  "output": 0.40},
    # GPT (на случай подключения)
    "gpt-4o":                         {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":                    {"input": 0.15,  "output": 0.60},
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Считает стоимость одного вызова в USD."""
    prices = MODEL_PRICES.get(model)
    if not prices:
        return 0.0
    input_cost  = (prompt_tokens     / 1_000_000) * prices["input"]
    output_cost = (completion_tokens / 1_000_000) * prices["output"]
    return round(input_cost + output_cost, 6)
