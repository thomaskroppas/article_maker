import re
from typing import List


def count_words(text: str) -> int:
    """Считает слова без markdown-разметки."""
    clean = re.sub(r"[#*`_\[\]()>~\-]", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return len(clean.split()) if clean else 0


def check_word_count(actual: int, target: int, tolerance: float = 0.20) -> str:
    """
    Возвращает 'ok', 'warn' или 'fail' по отклонению от цели.
    """
    if target == 0:
        return "ok"
    deviation = abs(actual - target) / target
    if deviation <= 0.10:
        return "ok"
    if deviation <= tolerance:
        return "warn"
    return "fail"


def sum_sections(word_counts: List[int]) -> int:
    return sum(word_counts)
