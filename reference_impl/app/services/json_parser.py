"""
Безопасное извлечение JSON из LLM-ответов.
LLM часто оборачивает JSON в ```json ... ``` или добавляет текст вокруг.
"""
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _try_parse(text: str) -> Optional[dict | list]:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _scan_balanced(text: str, start_idx: int) -> Optional[int]:
    """
    Идёт от позиции '{' и ищет парную закрывающую '}', учитывая:
      - строковые литералы в двойных кавычках (внутри них фигурные скобки игнорируем);
      - экранированные кавычки \\".
    Возвращает индекс '}' или None если не закрыто.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
    return None


def _unclosed_depth(text: str, start_idx: int) -> int:
    """
    Считает сколько '}' не хватает для закрытия блока, начиная с start_idx.
    Учитывает строки и экранирование. Возвращает остаточную глубину.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    return depth


def extract_json(text: str) -> Optional[dict]:
    """
    Достаёт JSON из произвольного LLM-ответа.
    Шаги:
      1. Прямой парсинг текста.
      2. Снять ```json ... ``` обёртку.
      3. Найти первый сбалансированный { ... } блок с учётом строк.
      4. Если блок не закрылся (обрезанный ответ) — дописать недостающие '}'.
    """
    if not text or not text.strip():
        return None

    # 1. Прямой парсинг
    result = _try_parse(text)
    if result is not None:
        return result

    # 2. Снять ```json ... ``` или ``` ... ``` обёртку
    clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    clean = re.sub(r"\s*```\s*$", "", clean.strip(), flags=re.MULTILINE).strip()
    result = _try_parse(clean)
    if result is not None:
        return result

    # 3. Сбалансированный поиск первого валидного { ... } блока.
    # Внутри строк '{' и '}' не считаем — это исправляет F2.
    for i, ch in enumerate(text):
        if ch != '{':
            continue
        end = _scan_balanced(text, i)
        if end is None:
            continue
        candidate = text[i:end + 1]
        result = _try_parse(candidate)
        if result is not None:
            return result

    # 4. Если первый '{' есть, но баланс не сошёлся — JSON обрезан.
    # Дописываем недостающие '}'. depth считается заново от первого '{',
    # независимо от предыдущих шагов — это исправляет F3.
    first_brace = text.find('{')
    if first_brace >= 0:
        depth = _unclosed_depth(text, first_brace)
        if depth > 0:
            truncated = text[first_brace:] + "}" * depth
            result = _try_parse(truncated)
            if result is not None:
                logger.warning("JSON был обрезан — восстановлен автоматически")
                return result

    logger.warning("Не удалось извлечь JSON из ответа LLM")
    logger.debug(f"Сырой текст: {text[:500]}")
    return None


def parse_strict(text: str, schema_class) -> object:
    data = extract_json(text)
    if data is None:
        raise ValueError(f"Не удалось извлечь JSON из ответа:\n{text[:300]}")
    try:
        return schema_class(**data)
    except Exception as e:
        raise ValueError(f"Ошибка валидации схемы {schema_class.__name__}: {e}\nДанные: {data}")
