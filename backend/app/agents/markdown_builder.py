"""Сборка markdown из финальных секций — ТЗ §6.10."""

from __future__ import annotations

from ..schemas import FullDraft, Outline, SectionFinal
from .text_utils import count_words, extract_summary, strip_leading_heading

_NO_HEADING = (
    "quick_answer",
    "quick answer",
    "intro",
    "быстрый ответ",
    "краткий ответ",
)
_FAQ_MARKERS = ("faq", "вопрос")


def is_no_heading_section(section_id: str, title: str = "") -> bool:
    blob = f"{section_id} {title}".lower()
    return any(kw in blob for kw in _NO_HEADING)


def has_faq_in_sections(outline: Outline) -> bool:
    return any(
        any(m in s.section_id.lower() or m in s.title.lower() for m in _FAQ_MARKERS)
        for s in outline.sections
    )


def assemble_draft(outline: Outline, final_sections: dict[str, str]) -> FullDraft:
    lines = [f"# {outline.h1}", ""]
    assembled: list[SectionFinal] = []

    for spec in outline.sections:
        text = final_sections.get(spec.section_id, "")
        if not text.strip():
            raise ValueError(f"Секция {spec.section_id} пустая — сборка невозможна")
        text, _ = extract_summary(text)  # страховка от просочившегося маркера
        clean = strip_leading_heading(text).strip()

        if is_no_heading_section(spec.section_id, spec.title):
            lines += [clean, ""]
        else:
            prefix = "##" if spec.level == "H2" else "###"
            lines += [f"{prefix} {spec.title}", "", clean, ""]

        assembled.append(
            SectionFinal(section_id=spec.section_id, title=spec.title, content=clean)
        )

    markdown = "\n".join(lines)
    return FullDraft(
        h1=outline.h1,
        content_markdown=markdown,
        sections=assembled,
        word_count=count_words(markdown),
        section_count=len(assembled),
    )
