"""
Единый интерфейс для вызова LLM.
Скрывает различия между OpenAI, Anthropic и Google.
"""
from __future__ import annotations
import logging
from typing import Optional
from app.config.llm_settings import (
    PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_GOOGLE,
    AGENT_MODELS, AGENT_PARAMS,
    DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)

# Импорт счётчика стоимости
from app.services.cost_tracker import cost_tracker


class LLMResponse:
    def __init__(self, text: str, prompt_tokens: int = 0,
                 completion_tokens: int = 0):
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class LLMClient:
    """
    Вызывает нужного провайдера в зависимости от имени агента.
    """
    def __init__(self):
        self._anthropic = None
        self._openai    = None
        self._google    = None

    # ─── Ленивая инициализация клиентов ──────────────────────────────────

    def _get_anthropic(self):
        if self._anthropic is None:
            import anthropic
            from app.config.settings import ANTHROPIC_API_KEY
            self._anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        return self._anthropic

    def _get_openai(self):
        if self._openai is None:
            from openai import OpenAI
            from app.config.settings import OPENAI_API_KEY
            self._openai = OpenAI(api_key=OPENAI_API_KEY)
        return self._openai

    def _get_google(self):
        if self._google is None:
            import google.generativeai as genai
            from app.config.settings import GOOGLE_API_KEY
            genai.configure(api_key=GOOGLE_API_KEY)
            self._google = genai
        return self._google

    # ─── Вызов по имени агента ────────────────────────────────────────────

    def call(self, agent_name: str, prompt: str,
             system_prompt: Optional[str] = None) -> LLMResponse:
        """
        Главный метод. Выбирает провайдер и модель по agent_name.
        """
        cfg    = AGENT_MODELS[agent_name]
        params = AGENT_PARAMS.get(agent_name, {})
        provider = cfg["provider"]
        model    = cfg["model"]
        max_tok  = params.get("max_tokens", DEFAULT_MAX_TOKENS)
        temp     = params.get("temperature", DEFAULT_TEMPERATURE)

        logger.debug(f"[{agent_name}] → {provider}/{model}, max_tokens={max_tok}")

        if provider == PROVIDER_ANTHROPIC:
            resp = self._call_anthropic(model, prompt, system_prompt, max_tok, temp)
        elif provider == PROVIDER_OPENAI:
            resp = self._call_openai(model, prompt, system_prompt, max_tok, temp)
        elif provider == PROVIDER_GOOGLE:
            resp = self._call_google(model, prompt, system_prompt, max_tok, temp)
        else:
            raise ValueError(f"Неизвестный провайдер: {provider}")

        # Считаем стоимость запроса
        cost_tracker.add(agent_name, model, resp.prompt_tokens, resp.completion_tokens)
        return resp

    # ─── Anthropic ────────────────────────────────────────────────────────

    def _call_anthropic(self, model: str, prompt: str,
                        system: Optional[str], max_tokens: int,
                        temperature: float) -> LLMResponse:
        client = self._get_anthropic()
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system

        resp = client.messages.create(**kwargs)
        text = resp.content[0].text
        return LLMResponse(
            text=text,
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
        )

    # ─── OpenAI ───────────────────────────────────────────────────────────

    def _call_openai(self, model: str, prompt: str,
                     system: Optional[str], max_tokens: int,
                     temperature: float) -> LLMResponse:
        client = self._get_openai()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content
        return LLMResponse(
            text=text,
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
        )

    # ─── Google Gemini ────────────────────────────────────────────────────

    def _call_google(self, model: str, prompt: str,
                     system: Optional[str], max_tokens: int,
                     temperature: float) -> LLMResponse:
        genai = self._get_google()
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        gen_model = genai.GenerativeModel(model)
        config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        resp = gen_model.generate_content(full_prompt, generation_config=config)
        text = resp.text
        # Google не всегда даёт токены в бесплатном API
        pt = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
        ct = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
        return LLMResponse(text=text, prompt_tokens=pt, completion_tokens=ct)
