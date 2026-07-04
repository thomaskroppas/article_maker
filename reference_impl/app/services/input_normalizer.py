"""
input_normalizer — нормализует и валидирует article_input из GUI.
Не использует LLM — это чистая программная логика.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from app.schemas.article_input import ArticleInput
from app.utils.ids import generate_article_id

logger = logging.getLogger(__name__)


class ValidationResult:
    def __init__(self, success: bool,
                 article_input: Optional[ArticleInput] = None,
                 errors: Optional[list] = None):
        self.success = success
        self.article_input = article_input
        self.errors = errors or []

    def __bool__(self):
        return self.success


def normalize(raw: dict) -> ValidationResult:
    """
    Принимает сырой dict из GUI, нормализует и возвращает
    ValidationResult с готовым ArticleInput или списком ошибок.
    """
    # 1. Генерируем системные поля
    now = datetime.now(timezone.utc).isoformat()
    raw.setdefault("article_id", generate_article_id())
    raw.setdefault("created_at", now)
    raw.setdefault("updated_at", now)
    raw.setdefault("status", "created")
    raw.setdefault("pipeline_version", "v1")
    raw.setdefault("prompt_set_version", "v1")

    # 2. Базовая нормализация строк
    for field in ("article_title", "main_keyword", "geo", "optional_notes"):
        if field in raw and isinstance(raw[field], str):
            raw[field] = raw[field].strip()

    # 3. target_word_count → int
    if "target_word_count" in raw:
        try:
            raw["target_word_count"] = int(raw["target_word_count"])
        except (ValueError, TypeError):
            pass

    # 3a. Автоопределение интента, если юзер не задал явно.
    # Пустая строка из dropdown «— определить автоматически —» сюда тоже падает.
    if not raw.get("intent"):
        from app.services.intent_detector import detect_intent
        detected = detect_intent(raw.get("article_title") or raw.get("main_keyword"))
        raw["intent"] = detected
        logger.info(f"Интент определён автоматически: {detected}")

    # 4. Валидация через Pydantic
    try:
        obj = ArticleInput(**raw)
        logger.info(f"article_input валиден: {obj.article_id}")
        return ValidationResult(success=True, article_input=obj)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            field = " → ".join(str(x) for x in err["loc"])
            msg = err["msg"]
            errors.append(f"{field}: {msg}")
        logger.warning(f"Ошибки валидации: {errors}")
        return ValidationResult(success=False, errors=errors)
