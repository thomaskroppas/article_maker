"""T-4: сохранение промпта и ответа LLM на диск (ТЗ §6.2)."""

from __future__ import annotations

from app.llm import save_llm_interaction


def test_save_llm_interaction(tmp_path):
    d = save_llm_interaction(
        tmp_path / "prompts", "brief_agent", "PROMPT TEXT", "RESPONSE TEXT"
    )
    assert (d / "brief_agent_prompt.txt").read_text(encoding="utf-8") == "PROMPT TEXT"
    assert (d / "brief_agent_response.txt").read_text(encoding="utf-8") == "RESPONSE TEXT"


def test_save_with_suffix(tmp_path):
    d = save_llm_interaction(
        tmp_path, "writer_agent", "p", "r", suffix="_s0_1"
    )
    assert (d / "writer_agent_s0_1_prompt.txt").exists()
    assert (d / "writer_agent_s0_1_response.txt").exists()
