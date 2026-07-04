"""LLM-клиенты: Anthropic (боевой) и Mock (fixtures, офлайн).

ТЗ §7.1 (контракт), §7.2 (модели/параметры), §14.1. Живые вызовы Anthropic —
только в T-14; во всех остальных задачах пайплайн гоняется на MockLLMClient.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..paths import fixtures_dir, reference_dir
from .cost import CostTracker
from .models import get_model_params
from .retry import with_retry


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class BaseLLMClient(ABC):
    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        self.cost_tracker = cost_tracker

    @abstractmethod
    def call(
        self, agent_name: str, prompt: str, system_prompt: Optional[str] = None
    ) -> LLMResponse: ...

    def _track(self, agent_name: str, resp: LLMResponse) -> None:
        if self.cost_tracker is not None:
            self.cost_tracker.add(
                agent_name, resp.model, resp.prompt_tokens, resp.completion_tokens
            )


class AnthropicLLMClient(BaseLLMClient):
    """Боевой клиент Anthropic. Ленивая инициализация SDK, ретраи 429/500."""

    def __init__(
        self,
        api_key: str,
        cost_tracker: Optional[CostTracker] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ):
        super().__init__(cost_tracker)
        self._api_key = api_key
        self._stop_flag = stop_flag
        self._client = None

    def _anthropic(self):
        if self._client is None:
            import anthropic  # ленивый импорт — не нужен для Mock-прогонов

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def call(
        self, agent_name: str, prompt: str, system_prompt: Optional[str] = None
    ) -> LLMResponse:
        model, max_tokens, temperature = get_model_params(agent_name)
        client = self._anthropic()

        def _do_call() -> LLMResponse:
            kwargs = dict(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            if system_prompt:
                kwargs["system"] = system_prompt
            resp = client.messages.create(**kwargs)
            return LLMResponse(
                text=resp.content[0].text,
                prompt_tokens=resp.usage.input_tokens,
                completion_tokens=resp.usage.output_tokens,
                model=model,
            )

        resp = with_retry(_do_call, stop_flag=self._stop_flag)
        self._track(agent_name, resp)
        return resp


class MockResponseNotConfigured(KeyError):
    pass


def _default_mock_registry() -> dict[str, str]:
    """Ответы по имени агента для полного офлайн-прогона (ТЗ «MockLLMClient»).

    Аналитические шаги 2–5 — из fixtures/; шаги 6–13 — правдоподобные заглушки
    (sources_weaver специально возвращает пустое → weave_sources откатится к
    оригиналу без вставки ссылок).
    """
    fx = fixtures_dir()
    ref = reference_dir()
    out: dict[str, str] = {}
    for agent, fname in {
        "competitor_analysis_agent": "competitor_analysis_example.json",
        "lsi_agent": "lsi_example.json",
        "brief_agent": "brief_example.json",
        "outline_agent": "outline_example.json",
    }.items():
        p = Path(fx) / fname
        if p.exists():
            out[agent] = p.read_text(encoding="utf-8")

    out["writer_agent"] = (
        "## Раздел\nСодержательный текст секции о теме статьи с фактами и цифрами. "
        "Раскрывает суть вопроса и полезен читателю.\n"
        "<!-- SUMMARY: ключевой факт секции -->"
    )
    out["critic_agent"] = json.dumps(
        {"overall_score": 82, "per_criterion": {}, "issues": [], "suggestions": []}
    )
    out["editor_agent"] = "## Раздел\nУлучшенный содержательный текст секции."
    out["faq_writer_agent"] = "## FAQ\n**Частый вопрос?**\nПрямой ответ на вопрос."
    out["image_keys_agent"] = json.dumps(
        ["baikal lake", "siberia nature", "deep water", "russia landscape", "clear water"]
    )
    # пустой ответ → weave_sources сочтёт текст неизменённым только при совпадении;
    # здесь пусто → откат к оригиналу (без ссылок), пайплайн не падает.
    out["sources_weaver_agent"] = json.dumps({"article_markdown": "", "links": []})
    out["fact_checker_agent"] = json.dumps(
        {"statements": [
            {"text": "Байкал — озеро в Сибири.", "type": "location",
             "subject": "Байкал", "property": None, "value_in_article": "Сибирь"}
        ]}
    )
    out["final_qa_agent"] = json.dumps(
        {"brief_alignment": 82, "intent_coverage": 85, "factuality": 80,
         "recommendation": "Статья готова к ручной проверке."}
    )
    fp = Path(ref) / "final_package.json"
    if fp.exists():
        out["metadata_agent"] = fp.read_text(encoding="utf-8")
    return out


class MockLLMClient(BaseLLMClient):
    """Оффлайн-клиент: возвращает содержимое fixtures по имени агента.

    `responses` дополняет/переопределяет дефолтный реестр (используется в T-6/T-8
    для агентов без прямого fixture). Токены оцениваются грубо (≈4 символа/токен),
    чтобы работал учёт стоимости.
    """

    def __init__(
        self,
        responses: Optional[dict[str, str]] = None,
        cost_tracker: Optional[CostTracker] = None,
    ):
        super().__init__(cost_tracker)
        self.registry = _default_mock_registry()
        if responses:
            self.registry.update(responses)

    def set_response(self, agent_name: str, text: str) -> None:
        self.registry[agent_name] = text

    def call(
        self, agent_name: str, prompt: str, system_prompt: Optional[str] = None
    ) -> LLMResponse:
        if agent_name not in self.registry:
            raise MockResponseNotConfigured(
                f"MockLLMClient: нет заготовленного ответа для '{agent_name}'"
            )
        model, _, _ = get_model_params(agent_name)
        text = self.registry[agent_name]
        resp = LLMResponse(
            text=text,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            model=model,
        )
        self._track(agent_name, resp)
        return resp
