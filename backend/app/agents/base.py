"""Базовый агент (ТЗ §7.1): рендер промпта → вызов LLM → парсинг JSON.

Без Qt/глобального состояния desktop-версии. Сохранение промпта/ответа на диск —
через llm.save_llm_interaction в оркестраторе (T-7).
"""

from __future__ import annotations

from typing import Any, Optional

from ..llm import render_prompt
from ..llm.client import BaseLLMClient, LLMResponse
from .json_parse import extract_json


class BaseAgent:
    agent_name: str = ""

    def __init__(self, llm: BaseLLMClient):
        self.llm = llm
        self.last_prompt: str = ""
        self.last_response: str = ""

    def _call(self, variables: dict, system_prompt: Optional[str] = None) -> LLMResponse:
        prompt = render_prompt(self.agent_name, variables)
        self.last_prompt = prompt
        resp = self.llm.call(self.agent_name, prompt, system_prompt)
        self.last_response = resp.text
        return resp

    def _parse_json(self, text: str) -> Any:
        data = extract_json(text)
        if data is None:
            raise ValueError(
                f"[{self.agent_name}] не удалось распарсить JSON из ответа:\n{text[:400]}"
            )
        return data
