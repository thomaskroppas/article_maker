"""image_finder — точки вставки и вставка картинок в markdown (ТЗ §6.11)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from ..agents.text_utils import count_words
from .processor import process_image
from .providers import ImageProvider, pick_image

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$")
_IMAGE_RE = re.compile(r"<!--\s*IMAGE:.*?-->")
_SKIP_TITLES = ("faq", "вопрос", "заключ", "итог", "источник", "conclusion")
_MIN_SECTION_WORDS = 60


def find_insertion_points(markdown: str) -> list[tuple[str, int]]:
    """Список (kind, line_index): 'placeholder' — строка с <!-- IMAGE -->,
    'heading' — строка H2/H3, после которой уместна картинка (§6.11)."""
    lines = markdown.split("\n")
    points: list[tuple[str, int]] = []

    for i, line in enumerate(lines):
        if _IMAGE_RE.search(line):
            points.append(("placeholder", i))

    heads = [(i, m) for i, line in enumerate(lines) if (m := _HEADING_RE.match(line))]
    for k, (i, m) in enumerate(heads):
        title = m.group(2).strip().lower()
        if any(s in title for s in _SKIP_TITLES):
            continue
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = " ".join(lines[i + 1 : end])
        if count_words(body) >= _MIN_SECTION_WORDS:
            points.append(("heading", i))

    # по возрастанию line_index
    return sorted(points, key=lambda p: p[1])


def _default_download(url: str) -> bytes:
    import requests

    return requests.get(url, timeout=20).content


def run_image_stage(
    markdown: str,
    article_input,
    keys: list[str],
    providers: list[ImageProvider],
    *,
    article_dir: str | Path,
    downloader: Optional[Callable[[str], bytes]] = None,
    processor: Callable[[bytes], bytes] = process_image,
    max_images: int = 8,
) -> str:
    """Вставить картинки в точки вставки. Дедуп по URL, ротация ключей — в провайдерах."""
    if not keys or not providers:
        return markdown
    download = downloader or _default_download
    images_dir = Path(article_dir) / "images"

    points = find_insertion_points(markdown)[:max_images]
    if not points:
        return markdown

    lines = markdown.split("\n")
    used_urls: set[str] = set()
    inserts: dict[int, str] = {}  # line_index -> markdown-сниппет
    replace: set[int] = set()  # индексы строк-плейсхолдеров на замену
    n = 0

    for kind, idx in points:
        query = keys[n % len(keys)]
        hit = pick_image(providers, query, article_input.language, used_urls)
        if not hit:
            continue
        try:
            processed = process_image_bytes(download(hit.url), processor)
        except Exception:  # noqa: BLE001 — битую картинку просто пропускаем
            continue
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / f"{n}.webp").write_bytes(processed)
        snippet = (
            f"![{hit.alt or article_input.main_keyword}](images/{n}.webp)\n"
            f"*Источник: [{hit.provider}]({hit.source_url})*"
        )
        if kind == "placeholder":
            replace.add(idx)
            inserts[idx] = snippet
        else:
            inserts[idx] = snippet
        n += 1

    out: list[str] = []
    for i, line in enumerate(lines):
        if i in replace:
            out.append(inserts[i])
            continue
        out.append(line)
        if i in inserts and i not in replace:
            out.append("")
            out.append(inserts[i])
    return "\n".join(out)


def process_image_bytes(raw: bytes, processor: Callable[[bytes], bytes]) -> bytes:
    return processor(raw)
