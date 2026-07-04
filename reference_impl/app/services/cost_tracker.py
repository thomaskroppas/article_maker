"""
CostTracker — считает расходы на LLM в реальном времени.
Хранит расход по сессии и по каждой статье отдельно.
Общий накопленный расход сохраняется в БД.
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional
from app.config.llm_settings import calculate_cost

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    agent:             str
    model:             str
    prompt_tokens:     int
    completion_tokens: int
    cost_usd:          float


class CostTracker:
    """
    Синглтон — один экземпляр на всё приложение.
    Обновляет GUI через callback в реальном времени.
    """
    _instance: Optional["CostTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.session_cost:  float = 0.0   # с момента запуска приложения
        self.article_cost:  float = 0.0   # текущая статья
        self.total_cost:    float = self._load_total()
        self.last_call_cost: float = 0.0
        self.current_article_id: Optional[str] = None
        self.calls: list[CallRecord] = []
        self._on_update: Optional[Callable[[], None]] = None

    # ─── Публичные методы ─────────────────────────────────────────────────

    def set_callback(self, cb: Callable[[], None]):
        """GUI регистрирует коллбэк для обновления отображения."""
        self._on_update = cb

    def reset_article(self, article_id: str = None):
        """Сбросить счётчик текущей статьи при старте нового пайплайна.
        article_id — если задан, последующие add() будут писать cost в БД для этой статьи.
        """
        self.article_cost = 0.0
        self.calls.clear()
        self.current_article_id = article_id

    def add(self, agent: str, model: str,
            prompt_tokens: int, completion_tokens: int):
        """Добавить запись о вызове LLM."""
        cost = calculate_cost(model, prompt_tokens, completion_tokens)

        self.last_call_cost = cost
        self.article_cost   = round(self.article_cost + cost, 6)
        self.session_cost   = round(self.session_cost + cost, 6)
        self.total_cost     = round(self.total_cost + cost, 6)

        self.calls.append(CallRecord(
            agent=agent, model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        ))

        self._save_total()
        # Параллельно сохраняем накопленный cost_usd для текущей статьи в БД,
        # чтобы потом видеть расход в аналитике per article.
        if self.current_article_id:
            try:
                from app.storage.repositories import update_article_cost
                update_article_cost(self.current_article_id, self.article_cost)
            except Exception as e:
                logger.warning(f"[cost] не удалось сохранить в БД: {e}")
        logger.debug(
            f"[cost] {agent} | {model} | "
            f"in={prompt_tokens} out={completion_tokens} | "
            f"${cost:.5f} | article=${self.article_cost:.4f}"
        )

        if self._on_update:
            self._on_update()

    # ─── Форматирование для GUI ────────────────────────────────────────────

    def format_status(self) -> str:
        return (
            f"Статья: ${self.article_cost:.4f}  │  "
            f"Сессия: ${self.session_cost:.4f}  │  "
            f"Всего: ${self.total_cost:.4f}  │  "
            f"Последний запрос: ${self.last_call_cost:.5f}"
        )

    # ─── Сохранение накопленной суммы ─────────────────────────────────────

    def _total_file(self):
        from app.config.settings import DATA_DIR
        return DATA_DIR / "total_cost.txt"

    def _load_total(self) -> float:
        try:
            return float(self._total_file().read_text().strip())
        except Exception:
            return 0.0

    def _save_total(self):
        try:
            self._total_file().write_text(str(self.total_cost))
        except Exception:
            pass


# Глобальный экземпляр
cost_tracker = CostTracker()
