"""Извлечение JSON из ответа LLM (устойчиво к обёрткам ```json и тексту вокруг)."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

_FENCE = re.compile(r"^```[a-zA-Z0-9_]*\s*\n?|\n?```$")


def extract_json(text: str) -> Optional[Any]:
    if text is None:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = _FENCE.sub("", s).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass
    # Поиск первого сбалансированного объекта/массива.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = s.find(open_ch)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start : i + 1])
                    except Exception:  # noqa: BLE001
                        break
    return None
