"""
Базовый класс агента. Инкапсулирует LLM-вызов + retry + логирование промптов.
"""
import logging
from typing import Optional, Callable
from app.llm.llm_client import LLMClient, LLMResponse
from app.prompts.prompt_loader import render_prompt
from app.services.retry_service import with_retry
from app.services.json_parser import extract_json

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Каждый агент наследует этот класс и реализует метод run().
    """
    agent_name: str = ""

    def __init__(self, llm_client: LLMClient,
                 stop_flag: Optional[Callable[[], bool]] = None):
        self.llm = llm_client
        self._stop_flag = stop_flag
        self._last_prompt: str = ""
        self._last_response: str = ""

    def set_stop_flag(self, stop_flag: Callable[[], bool]):
        """Устанавливает флаг остановки — вызывается из оркестратора."""
        self._stop_flag = stop_flag

    def _call(self, variables: dict,
              system_prompt: Optional[str] = None) -> LLMResponse:
        """Рендерит промпт и вызывает LLM с retry."""
        prompt = render_prompt(self.agent_name, variables)
        self._last_prompt = prompt

        def _do_call():
            return self.llm.call(self.agent_name, prompt, system_prompt)

        resp = with_retry(_do_call, step_name=self.agent_name,
                          stop_flag=self._stop_flag)
        self._last_response = resp.text
        logger.debug(
            f"[{self.agent_name}] tokens: "
            f"{resp.prompt_tokens}→{resp.completion_tokens}"
        )
        return resp

    def _parse_json(self, text: str) -> dict:
        """Извлекает JSON из ответа LLM."""
        data = extract_json(text)
        if data is None:
            raise ValueError(
                f"[{self.agent_name}] Не удалось распарсить JSON:\n{text[:400]}"
            )
        return data

    @property
    def last_prompt(self) -> str:
        return self._last_prompt

    @property
    def last_response(self) -> str:
        return self._last_response
