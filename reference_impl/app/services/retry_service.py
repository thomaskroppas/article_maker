"""
Retry-логика для LLM-вызовов и HTTP-запросов.
"""
import time
import logging
from typing import Callable, TypeVar, Optional
from app.config.pipeline_settings import MAX_RETRY_ATTEMPTS, RETRY_DELAY_SECONDS

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _is_overload(exc: Exception) -> bool:
    """Проверяет является ли ошибка перегрузкой сервера (529)."""
    msg = str(exc).lower()
    return "529" in msg or "overloaded" in msg or "overload" in msg


def _interruptible_sleep(seconds: float, stop_flag=None, interval: float = 0.5):
    """
    Спит seconds секунд, но каждые interval секунд проверяет stop_flag.
    Если флаг установлен — прерывает сон досрочно.
    """
    elapsed = 0.0
    while elapsed < seconds:
        if stop_flag is not None and stop_flag():
            return
        chunk = min(interval, seconds - elapsed)
        time.sleep(chunk)
        elapsed += chunk


def with_retry(func: Callable[..., T], *args,
               max_attempts: int = MAX_RETRY_ATTEMPTS,
               delay: float = RETRY_DELAY_SECONDS,
               step_name: str = "",
               stop_flag: Optional[Callable[[], bool]] = None,
               **kwargs) -> T:
    """
    Выполняет func с retry при исключении.

    При 529 Overloaded — ждёт дольше (до 60 сек) и делает больше попыток.
    stop_flag() — если возвращает True, прерывает retry немедленно.
    Бросает последнее исключение если все попытки исчерпаны.
    """
    last_exc = None
    label = f"[{step_name}] " if step_name else ""

    overload_extra_attempts = 3
    attempt = 0
    overload_attempts = 0
    regular_attempts = 0

    while True:
        # Проверяем stop_flag перед каждой попыткой
        if stop_flag is not None and stop_flag():
            logger.info(f"{label}Остановка запрошена — прерываем retry")
            if last_exc:
                raise last_exc
            raise InterruptedError("Pipeline stopped by user")

        attempt += 1
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            is_overload = _is_overload(e)

            if is_overload:
                overload_attempts += 1
                if overload_attempts > overload_extra_attempts:
                    break
                wait = min(15 * overload_attempts, 60)
                logger.warning(
                    f"{label}Сервер перегружен (попытка {overload_attempts}/"
                    f"{overload_extra_attempts}), ждём {wait} сек..."
                )
                _interruptible_sleep(wait, stop_flag)
            else:
                regular_attempts += 1
                if regular_attempts >= max_attempts:
                    break
                wait = delay * regular_attempts
                logger.warning(
                    f"{label}Попытка {regular_attempts}/{max_attempts} не удалась: {e}"
                )
                _interruptible_sleep(wait, stop_flag)

    raise last_exc
