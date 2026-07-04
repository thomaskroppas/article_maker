"""Модели, параметры вызовов и цены по агентам — ТЗ §7.2, §14.1.

Значения зафиксированы ТЗ (§6.2.1 константы, §7.2 per-agent параметры) и
reference_impl. Не менять без согласования с заказчиком.
"""

from __future__ import annotations

PROVIDER_ANTHROPIC = "anthropic"

# Модели (ТЗ §14.1): основная — Sonnet 4.6, дешёвая — Haiku 4.5.
CLAUDE_SONNET_MODEL = "claude-sonnet-4-6"
CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.7

_S = CLAUDE_SONNET_MODEL
_H = CLAUDE_HAIKU_MODEL

# agent_name -> {"provider", "model"}
AGENT_MODELS: dict[str, dict[str, str]] = {
    "competitor_analysis_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "lsi_agent": {"provider": PROVIDER_ANTHROPIC, "model": _H},
    "brief_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "outline_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "writer_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "critic_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "editor_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "faq_writer_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "sources_weaver_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "fact_checker_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "image_keys_agent": {"provider": PROVIDER_ANTHROPIC, "model": _H},
    "final_qa_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "metadata_agent": {"provider": PROVIDER_ANTHROPIC, "model": _S},
    "archetype_picker_agent": {"provider": PROVIDER_ANTHROPIC, "model": _H},
    "style_extractor_agent": {"provider": PROVIDER_ANTHROPIC, "model": _H},
}

# per-agent параметры вызова — ТЗ §7.2 (таблица агентов).
AGENT_PARAMS: dict[str, dict[str, float]] = {
    "competitor_analysis_agent": {"max_tokens": 8192, "temperature": 0.3},
    "lsi_agent": {"max_tokens": 800, "temperature": 0.2},
    "brief_agent": {"max_tokens": 8192, "temperature": 0.4},
    "outline_agent": {"max_tokens": 8192, "temperature": 0.3},
    "writer_agent": {"max_tokens": 8192, "temperature": 0.7},
    "critic_agent": {"max_tokens": 4096, "temperature": 0.2},
    "editor_agent": {"max_tokens": 8192, "temperature": 0.6},
    "faq_writer_agent": {"max_tokens": 2000, "temperature": 0.6},
    "sources_weaver_agent": {"max_tokens": 4096, "temperature": 0.4},
    "fact_checker_agent": {"max_tokens": 4096, "temperature": 0.2},
    "image_keys_agent": {"max_tokens": 500, "temperature": 0.3},
    "final_qa_agent": {"max_tokens": 2048, "temperature": 0.2},
    "metadata_agent": {"max_tokens": 4096, "temperature": 0.4},
    "archetype_picker_agent": {"max_tokens": 512, "temperature": 0.1},
    "style_extractor_agent": {"max_tokens": 1500, "temperature": 0.3},
}

# Цены за 1M токенов, USD (источник — reference_impl/llm_settings, 8 июня 2026).
MODEL_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-7": {"input": 5.00, "output": 25.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    # предыдущее поколение — для совместимости со старыми записями
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
}


def get_model_params(agent_name: str) -> tuple[str, int, float]:
    """Вернуть (model, max_tokens, temperature) для агента."""
    model = AGENT_MODELS.get(agent_name, {}).get("model", CLAUDE_SONNET_MODEL)
    params = AGENT_PARAMS.get(agent_name, {})
    return (
        model,
        int(params.get("max_tokens", DEFAULT_MAX_TOKENS)),
        float(params.get("temperature", DEFAULT_TEMPERATURE)),
    )


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Стоимость одного вызова в USD по токенам (0.0 для неизвестной модели)."""
    prices = MODEL_PRICES.get(model)
    if not prices:
        return 0.0
    input_cost = (prompt_tokens / 1_000_000) * prices["input"]
    output_cost = (completion_tokens / 1_000_000) * prices["output"]
    return round(input_cost + output_cost, 6)
