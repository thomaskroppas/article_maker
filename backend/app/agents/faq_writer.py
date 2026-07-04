"""faq_writer_agent — шаг 9 (ТЗ §6.12, §7.3.8) + вставка/дедуп (FR-18)."""

from __future__ import annotations

import re
from typing import Optional

from ..schemas import Brief, Outline
from .base import BaseAgent
from .markdown_builder import has_faq_in_sections
from .writer import _author_block

# Заголовок «Заключение» на 6 языках (§6.12).
_CONCLUSION_RE = re.compile(
    r"^##\s+(заключен|итог|подводя|conclusion|conclusione|schluss|resumen|conclusión)",
    re.IGNORECASE | re.MULTILINE,
)


def _dedup_questions(questions: list[str]) -> list[str]:
    out: list[str] = []
    for q in questions:
        qs = (q or "").strip()
        if qs and qs.lower() not in {o.lower() for o in out}:
            out.append(qs)
    return out


def insert_faq(markdown: str, faq_block: str) -> str:
    """Вставить FAQ перед секцией Заключение; если её нет — в конец (§6.12)."""
    m = _CONCLUSION_RE.search(markdown)
    block = faq_block.strip()
    if m:
        return markdown[: m.start()].rstrip() + "\n\n" + block + "\n\n" + markdown[m.start():]
    return markdown.rstrip() + "\n\n" + block + "\n"


class FaqWriterAgent(BaseAgent):
    agent_name = "faq_writer_agent"

    def run(
        self,
        article_input,
        brief: Brief,
        article_markdown: str,
        questions: list[str],
        *,
        author: Optional[dict] = None,
    ) -> str:
        ai = article_input
        resp = self._call(
            {
                "article_title": ai.article_title,
                "main_keyword": ai.main_keyword,
                "article_summary": article_markdown[:1500],
                "lsi_keywords": ", ".join(brief.lsi_keywords),
                "author_block": _author_block(author),
                "questions": "\n".join(questions),
            }
        )
        return resp.text


def run_faq_stage(
    article_input,
    brief: Brief,
    outline: Outline,
    article_markdown: str,
    llm,
    *,
    author: Optional[dict] = None,
) -> str:
    """Сгенерировать и вставить FAQ. Дедуп: если FAQ уже есть в секциях —
    пропустить (FR-18); questions дедуплицируются.
    """
    if has_faq_in_sections(outline) or not outline.faq_section.enabled:
        return article_markdown
    questions = _dedup_questions(outline.faq_section.questions)
    if not questions:
        return article_markdown
    block = FaqWriterAgent(llm).run(article_input, brief, article_markdown, questions, author=author)
    return insert_faq(article_markdown, block)
