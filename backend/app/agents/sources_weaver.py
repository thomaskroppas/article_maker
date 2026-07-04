"""sources_weaver_agent — шаг 10 (ТЗ §6.13, §7.3.9, FR-13).

Агент вплетает 3-5 ссылок; КОД гарантирует инварианты: текст вне ссылок не
меняется (diff-проверка), ≤1 ссылка на секцию, живость URL (HEAD, 5 сек).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .base import BaseAgent

# inline-ссылка, НЕ картинка (не предваряется '!')
_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,4}\s+")


def unwrap_links(md: str) -> str:
    """Развернуть inline-ссылки обратно в текст (`[t](u)` → `t`), картинки не трогать."""
    return _LINK_RE.sub(lambda m: m.group(1), md)


def text_preserved(original: str, woven: str) -> bool:
    """True, если весь текст вне добавленных ссылок не изменён."""
    return unwrap_links(woven).strip() == unwrap_links(original).strip()


def extract_links(md: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _LINK_RE.finditer(md)]


def enforce_one_link_per_section(md: str, max_total: int = 5) -> str:
    """Оставить ≤1 ссылку на секцию и ≤max_total всего; лишние — развернуть."""
    lines = md.split("\n")
    out: list[str] = []
    section_has_link = False
    total = 0
    for line in lines:
        if _HEADING_RE.match(line):
            section_has_link = False
            out.append(line)
            continue

        def repl(m):
            nonlocal section_has_link, total
            if section_has_link or total >= max_total:
                return m.group(1)  # развернуть лишнюю
            section_has_link = True
            total += 1
            return m.group(0)

        out.append(_LINK_RE.sub(repl, line))
    return "\n".join(out)


def _default_url_alive(url: str) -> bool:
    import requests

    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        return resp.status_code < 400
    except Exception:  # noqa: BLE001
        return False


@dataclass
class WeaveResult:
    markdown: str
    links: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied: bool = True


class SourcesWeaverAgent(BaseAgent):
    agent_name = "sources_weaver_agent"

    def run(self, article_markdown, main_keyword, language, suggested_sources) -> dict:
        resp = self._call(
            {
                "article_markdown": article_markdown,
                "main_keyword": main_keyword,
                "language": language,
                "suggested_sources": json.dumps(suggested_sources, ensure_ascii=False),
            }
        )
        data = self._parse_json(resp.text)
        return data if isinstance(data, dict) else {}


def weave_sources(
    original: str,
    article_input,
    suggested_sources: list,
    llm,
    *,
    url_alive: Optional[Callable[[str], bool]] = None,
) -> WeaveResult:
    ai = article_input
    data = SourcesWeaverAgent(llm).run(original, ai.main_keyword, ai.language, suggested_sources)
    woven = data.get("article_markdown", "") if isinstance(data, dict) else ""
    warnings: list[str] = []

    # diff-проверка: если текст вне ссылок изменён — откатываемся к оригиналу.
    if not woven or not text_preserved(original, woven):
        return WeaveResult(original, [], ["sources_weaver изменил текст вне ссылок — вставка отклонена"], applied=False)

    # убрать мёртвые ссылки (HEAD)
    alive = url_alive or _default_url_alive
    for anchor, url in extract_links(woven):
        if not alive(url):
            woven = woven.replace(f"[{anchor}]({url})", anchor, 1)
            warnings.append(f"убран мёртвый URL: {url}")

    # гарантировать ≤1 ссылку на секцию и ≤5 всего
    woven = enforce_one_link_per_section(woven, max_total=5)
    links = extract_links(woven)
    if len(links) < 3:
        warnings.append(f"вплетено {len(links)} ссылок (<3)")
    return WeaveResult(woven, links, warnings, applied=True)
