"""Текстовые утилиты для сборки статьи."""

from __future__ import annotations

import re

_SUMMARY_RE = re.compile(r"<!--\s*SUMMARY:\s*(.+?)\s*-->", re.DOTALL)
_IMAGE_RE = re.compile(r"<!--\s*IMAGE:\s*(.+?)\s*-->", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,4}\s+")


def extract_summary(text: str) -> tuple[str, str]:
    """(текст без маркера, содержимое SUMMARY). Если маркера нет — (text, "")."""
    if not text:
        return text, ""
    m = _SUMMARY_RE.search(text)
    summary = m.group(1).strip() if m else ""
    cleaned = _SUMMARY_RE.sub("", text).rstrip()
    return cleaned, summary


def strip_leading_heading(text: str) -> str:
    """Убирает заголовок из начала текста, если Writer его добавил."""
    lines = text.strip().splitlines()
    if lines and _HEADING_RE.match(lines[0].strip()):
        remaining = "\n".join(lines[1:]).strip()
        return remaining or text
    return text


def count_words(text: str) -> int:
    # markdown-разметка/картинки не считаются словами
    plain = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    plain = re.sub(r"[#>*_`\-\[\]()]", " ", plain)
    return len(plain.split())
