"""Учёт стоимости LLM-вызовов (ТЗ §6.2 «Учёт стоимости LLM-вызова»).

В отличие от desktop-версии — без глобального синглтона и side-effect'ов в БД
(это ответственность оркестратора/репозиториев, T-7/T-11). Здесь — чистый
in-memory аккумулятор: один экземпляр на запуск пайплайна.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .models import calculate_cost


@dataclass
class CallRecord:
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass
class CostTracker:
    session_cost: float = 0.0
    article_cost: float = 0.0
    last_call_cost: float = 0.0
    calls: list[CallRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reset_article(self) -> None:
        with self._lock:
            self.article_cost = 0.0
            self.calls.clear()

    def add(
        self, agent: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        with self._lock:
            self.last_call_cost = cost
            self.article_cost = round(self.article_cost + cost, 6)
            self.session_cost = round(self.session_cost + cost, 6)
            self.calls.append(
                CallRecord(agent, model, prompt_tokens, completion_tokens, cost)
            )
        return cost

    @property
    def total_tokens_in(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def total_tokens_out(self) -> int:
        return sum(c.completion_tokens for c in self.calls)
