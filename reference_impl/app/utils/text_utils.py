import re


def count_words(text: str) -> int:
    """Считает слова, игнорируя markdown-разметку."""
    clean = re.sub(r"[#*`_\[\]()>~\-]", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return len(clean.split()) if clean else 0


def strip_markdown(text: str) -> str:
    """Удаляет базовую markdown-разметку."""
    text = re.sub(r"#+\s", "", text)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text.strip()


def truncate_text(text: str, max_words: int) -> str:
    """Обрезает текст до max_words слов."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def clean_lines(lines: list[str]) -> list[str]:
    """Убирает пустые строки и дубликаты."""
    seen = set()
    result = []
    for line in lines:
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return result


_SUMMARY_MARKER_RE = re.compile(
    r"<!--\s*SUMMARY:\s*(.+?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)


def extract_summary(text: str) -> tuple[str, str]:
    """
    Извлекает резюме из маркера <!-- SUMMARY: ... -->.
    Возвращает (текст без маркера, само резюме).
    Если маркера нет — возвращает (исходный текст, "").
    """
    if not text:
        return text, ""
    m = _SUMMARY_MARKER_RE.search(text)
    if not m:
        return text, ""
    summary = m.group(1).strip()
    cleaned = _SUMMARY_MARKER_RE.sub("", text).rstrip()
    return cleaned, summary


def slugify(text: str) -> str:
    """Преобразует текст в URL-slug (транслитерация для русского)."""
    # Таблица транслитерации
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
        "й": "j", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
        "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
    text = text.lower()
    result = []
    for ch in text:
        result.append(translit.get(ch, ch))
    text = "".join(result)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text
