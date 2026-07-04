"""T-4: MockLLMClient возвращает валидные схемы по имени агента + учёт стоимости."""

from __future__ import annotations

import json

import pytest

from app import schemas
from app.llm import CostTracker, MockLLMClient
from app.llm.client import MockResponseNotConfigured


def test_mock_returns_valid_schemas():
    mock = MockLLMClient()
    cases = {
        "competitor_analysis_agent": schemas.CompetitorAnalysisReport,
        "brief_agent": schemas.Brief,
        "outline_agent": schemas.Outline,
        "lsi_agent": schemas.LSIResult,
    }
    for agent, model in cases.items():
        resp = mock.call(agent, "prompt")
        data = json.loads(resp.text)
        assert model.model_validate(data) is not None


def test_mock_tracks_cost():
    ct = CostTracker()
    mock = MockLLMClient(cost_tracker=ct)
    mock.call("brief_agent", "some prompt text")
    assert ct.article_cost > 0
    assert len(ct.calls) == 1
    assert ct.calls[0].agent == "brief_agent"


def test_mock_unconfigured_agent_raises():
    mock = MockLLMClient()
    with pytest.raises(MockResponseNotConfigured):
        mock.call("writer_agent", "prompt")


def test_mock_custom_response_override():
    mock = MockLLMClient(responses={"writer_agent": "## Секция\nтекст"})
    resp = mock.call("writer_agent", "prompt")
    assert "Секция" in resp.text
    assert resp.model  # модель проставлена из AGENT_MODELS
