"""T-4: расчёт стоимости и аккумулятор CostTracker."""

from __future__ import annotations

from app.llm.cost import CostTracker
from app.llm.models import (
    CLAUDE_HAIKU_MODEL,
    CLAUDE_SONNET_MODEL,
    calculate_cost,
)


def test_sonnet_price():
    # 1M in + 1M out = $3 + $15 = $18
    assert calculate_cost(CLAUDE_SONNET_MODEL, 1_000_000, 1_000_000) == 18.0


def test_haiku_price():
    # 1M in + 1M out = $1 + $5 = $6
    assert calculate_cost(CLAUDE_HAIKU_MODEL, 1_000_000, 1_000_000) == 6.0


def test_unknown_model_is_free():
    assert calculate_cost("gpt-unknown", 1000, 1000) == 0.0


def test_small_call_rounding():
    # 1000 in + 500 out на Sonnet = 0.001*3 + 0.0005*15 = 0.003 + 0.0075 = 0.0105
    assert calculate_cost(CLAUDE_SONNET_MODEL, 1000, 500) == 0.0105


def test_cost_tracker_accumulates():
    ct = CostTracker()
    c1 = ct.add("brief_agent", CLAUDE_SONNET_MODEL, 1000, 500)
    c2 = ct.add("lsi_agent", CLAUDE_HAIKU_MODEL, 2000, 400)
    assert ct.last_call_cost == c2
    assert ct.article_cost == round(c1 + c2, 6)
    assert ct.session_cost == round(c1 + c2, 6)
    assert ct.total_tokens_in == 3000
    assert ct.total_tokens_out == 900
    assert len(ct.calls) == 2


def test_reset_article_keeps_session():
    ct = CostTracker()
    ct.add("brief_agent", CLAUDE_SONNET_MODEL, 1000, 500)
    session_before = ct.session_cost
    ct.reset_article()
    assert ct.article_cost == 0.0
    assert ct.calls == []
    assert ct.session_cost == session_before  # сессия не сбрасывается
