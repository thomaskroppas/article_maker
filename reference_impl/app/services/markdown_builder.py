"""
Собирает markdown-документ из финальных секций.
"""
import re
from typing import Dict
from app.schemas.outline import Outline
from app.schemas.output_schemas import FullDraft, SectionFinal
from app.services.word_count_service import count_words
from app.utils.text_utils import extract_summary

# Секции которые не получают заголовок H2/H3
_NO_HEADING_KEYWORDS = ("quick_answer", "quick answer", "intro", "intro_block",
                         "быстрый ответ", "краткий ответ")


def _is_no_heading_section(section_id: str, title: str = "") -> bool:
    """Проверяет и section_id и title — Claude может назвать секцию по-разному."""
    combined = (section_id + " " + title).lower()
    return any(kw in combined for kw in _NO_HEADING_KEYWORDS)


def _strip_leading_heading(text: str) -> str:
    """Убирает заголовок из начала текста если Writer его добавил."""
    lines = text.strip().splitlines()
    if not lines:
        return text
    first = lines[0].strip()
    if re.match(r'^#{1,4}\s+', first):
        remaining = "\n".join(lines[1:]).strip()
        return remaining if remaining else text
    return text


def assemble_draft(outline: Outline,
                   final_sections: Dict[str, str]) -> FullDraft:
    lines = [f"# {outline.h1}", ""]

    assembled_sections = []

    # Проверяем есть ли уже секция с FAQ в outline (по section_id или title).
    # Writer может создать секцию с section_id="s5" и title="FAQ — вопросы...",
    # тогда наш faq_writer_agent продублирует блок. Поэтому смотрим и на title.
    has_faq_section = any(
        "faq" in s.section_id.lower() or "faq" in s.title.lower()
        for s in outline.sections
    )

    for spec in outline.sections:
        sid  = spec.section_id
        text = final_sections.get(sid, "")

        if not text.strip():
            raise ValueError(f"Секция {sid} пустая — сборка невозможна")

        # Страховка: вырезаем маркер <!-- SUMMARY: ... --> если он каким-то
        # образом просочился мимо section_pipeline (нестандартный формат
        # ответа модели и т.п.) — чтобы он не оказался в готовом .md.
        text, _ = extract_summary(text)
        clean_text = _strip_leading_heading(text)

        # Quick Answer и intro-блоки — без заголовка
        if _is_no_heading_section(sid, spec.title):
            lines.append(clean_text.strip())
            lines.append("")
        else:
            prefix = "##" if spec.level == "H2" else "###"
            lines.append(f"{prefix} {spec.title}")
            lines.append("")
            lines.append(clean_text.strip())
            lines.append("")

        assembled_sections.append(SectionFinal(
            section_id=sid,
            title=spec.title,
            content=clean_text.strip(),
        ))

    # faq_section рендерится отдельным агентом faq_writer_agent в оркестраторе
    # (шаг 6.7 между картинками и final_qa). Здесь ничего не добавляем.

    full_markdown = "\n".join(lines)
    wc = count_words(full_markdown)

    return FullDraft(
        h1=outline.h1,
        content_markdown=full_markdown,
        sections=assembled_sections,
        word_count=wc,
        section_count=len(assembled_sections),
    )
