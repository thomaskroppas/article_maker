"""6 детерминированных QA-метрик (ТЗ §6.15).

length_control, completeness, keyword_usage, lsi_coverage, structure, readability.
Предложения делятся через pysbd (§8.2). Формулы — как в desktop-версии (веса и
пороги §6.15 / §6.2.1 не меняются).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_WORD_RE = re.compile(r"\b[\wа-яёА-ЯЁ]+\b", re.UNICODE)
# inline-ссылка, не картинка
_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\((https?://[^)\s]+)\)")

_STOPWORDS = {
    "в", "на", "у", "с", "к", "о", "об", "от", "до", "за", "по", "из",
    "и", "а", "но", "или", "же", "ли", "не", "ни", "что", "как", "где",
    "когда", "куда", "почему", "зачем", "это", "то", "так", "там", "тут",
    "для", "при", "со", "во",
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _content_words(phrase: str) -> list[str]:
    return [w for w in _words(phrase) if w not in _STOPWORDS and len(w) > 1]


def _split_sentences(text: str, language: str = "ru") -> list[str]:
    plain = re.sub(r"[#>*_`|\-]", " ", text)
    try:
        import pysbd

        seg = pysbd.Segmenter(language=language if language in _PYSBD_LANGS else "en", clean=False)
        return [s for s in seg.segment(plain) if s.strip()]
    except Exception:  # noqa: BLE001 — грубый фолбэк
        return [s for s in re.split(r"[.!?]+", plain) if s.strip()]


_PYSBD_LANGS = {"ru", "en", "de", "it", "es", "fr"}


# ─── 1. length_control (от суммы target секций, §6.15) ───
def calc_length_control(text: str, target_words: int) -> float:
    if target_words <= 0:
        return 100.0
    actual = _count_words(text)
    d = abs(actual - target_words) / target_words
    if d <= 0.05:
        s = 100.0
    elif d <= 0.10:
        s = 100 - (d - 0.05) / 0.05 * 15
    elif d <= 0.20:
        s = 85 - (d - 0.10) / 0.10 * 25
    elif d <= 0.30:
        s = 60 - (d - 0.20) / 0.10 * 30
    elif d <= 0.40:
        s = 30 - (d - 0.30) / 0.10 * 30
    else:
        s = 0.0
    return round(_clamp(s), 1)


# ─── 2. completeness ───
_ELEMENT_PATTERNS = {
    "faq": [r"(?im)^#{2,3}\s+.*(faq|вопрос)", r"(?i)\bfaq\b"],
    "table": [r"(?m)^\|.*\|"],
    "list": [r"(?m)^\s*[-*]\s+\S", r"(?m)^\s*\d+\.\s+\S"],
    "conclusion": [r"(?im)^#{2,3}\s+(заключ|итог|вывод|conclusion|подводя)"],
}


def count_external_links(markdown: str) -> int:
    """Число markdown-ссылок на внешние домены вне блока FAQ (для weaved_sources)."""
    # отрезаем блок FAQ (§6.15: ссылки считаются вне FAQ)
    m = re.search(r"(?im)^#{2,3}\s+.*(faq|вопрос)", markdown)
    body = markdown[: m.start()] if m else markdown
    count = 0
    for _anchor, url in _LINK_RE.findall(body):
        host = urlparse(url).netloc
        if host and "." in host:
            count += 1
    return count


def _element_present(text: str, element: str, required: list[str]) -> bool:
    key = element.lower().split()[0] if element else element
    if key == "quick_answer" or key == "quick":
        # интро-ответ: текст до первого H2 (после H1) >= 20 слов
        m = re.search(r"(?m)^##\s+", text)
        intro = text[: m.start()] if m else text
        intro = re.sub(r"(?m)^#\s+.*", "", intro).strip()
        return _count_words(intro) >= 20
    if key == "weaved_sources":
        return count_external_links(text) >= 3
    for pat in _ELEMENT_PATTERNS.get(key, []):
        if re.search(pat, text):
            return True
    return False


def calc_completeness(text: str, required_elements: list[str]) -> float:
    if not required_elements:
        return 100.0
    per = 100.0 / len(required_elements)
    score = sum(per for e in required_elements if _element_present(text, e, required_elements))
    return round(_clamp(score), 1)


# ─── 3. keyword_usage (main density*0.7 + secondary coverage*0.3) ───
def _keyword_density_score(text: str, keyword: str) -> float:
    tokens = _words(text)
    if not tokens or not keyword:
        return 0.0
    content = _content_words(keyword)
    if not content:
        return 0.0
    text_join = " ".join(tokens)
    hits = sum(len(re.findall(rf"\b{re.escape(w[:max(3, len(w)-2)])}\w*", text_join)) for w in content)
    density = hits / max(len(tokens), 1) / len(content)
    if 0.005 <= density <= 0.03:
        return 100.0
    if density < 0.005:
        return 70.0 if density > 0 else 0.0
    return 80.0 if density <= 0.05 else 60.0


def _coverage_score(text: str, keywords: list[str], tiers=((0.7, 100), (0.5, 80), (0.3, 50), (0.1, 30))) -> float:
    if not keywords:
        return 100.0
    text_join = " ".join(_words(text))
    found = 0
    for kw in keywords:
        content = _content_words(kw)
        if content and all(
            re.search(rf"\b{re.escape(w[:max(3, len(w)-2)])}\w*", text_join) for w in content
        ):
            found += 1
    cov = found / len(keywords)
    for thr, sc in tiers:
        if cov >= thr:
            return float(sc)
    return 20.0


def calc_keyword_usage(text: str, main_keyword: str, secondary: list[str]) -> float:
    main = _keyword_density_score(text, main_keyword)
    sec = _coverage_score(text, secondary)
    return round(_clamp(main * 0.7 + sec * 0.3), 1)


def calc_lsi_coverage(text: str, lsi_keywords: list[str]) -> float:
    if not lsi_keywords:
        return 100.0
    return round(
        _coverage_score(text, lsi_keywords, tiers=((0.6, 100), (0.4, 80), (0.25, 60), (0.1, 40))), 1
    )


# ─── 5. structure ───
def calc_structure(text: str) -> float:
    score = 0.0
    if re.search(r"(?m)^#\s+\S", text):
        score += 20
    h2 = len(re.findall(r"(?m)^##\s+\S", text))
    score += 40 if h2 >= 3 else 25 if h2 == 2 else 10 if h2 == 1 else 0
    if re.search(r"(?m)^###\s+\S", text):
        score += 20
    m = re.search(r"(?m)^##\s+", text)
    if m:
        intro = re.sub(r"(?m)^#\s+.*", "", text[: m.start()]).strip()
        if _count_words(intro) >= 30:
            score += 20
    return round(_clamp(score), 1)


# ─── 6. readability ───
def calc_readability(text: str, language: str = "ru") -> float:
    sentences = _split_sentences(text, language)
    if not sentences:
        return 50.0
    total = len(sentences)
    pct_long = sum(1 for s in sentences if _count_words(s) > 20) / total
    pct_short = sum(1 for s in sentences if _count_words(s) < 8) / total
    if pct_long <= 0.05:
        base = 100
    elif pct_long <= 0.10:
        base = 80
    elif pct_long <= 0.20:
        base = 60
    elif pct_long <= 0.30:
        base = 40
    else:
        base = 20
    penalty = 0 if pct_short <= 0.10 else 10 if pct_short <= 0.20 else 20
    return round(_clamp(base - penalty), 1)


@dataclass
class CodeMetrics:
    length_control: float
    completeness: float
    keyword_usage: float
    lsi_coverage: float
    structure: float
    readability: float
    details: dict


def calc_code_metrics(
    text: str,
    *,
    target_words: int,
    main_keyword: str,
    secondary_keywords: list[str],
    required_elements: list[str],
    lsi_keywords: list[str] | None = None,
    language: str = "ru",
) -> CodeMetrics:
    return CodeMetrics(
        length_control=calc_length_control(text, target_words),
        completeness=calc_completeness(text, required_elements),
        keyword_usage=calc_keyword_usage(text, main_keyword, secondary_keywords),
        lsi_coverage=calc_lsi_coverage(text, lsi_keywords or []),
        structure=calc_structure(text),
        readability=calc_readability(text, language),
        details={
            "actual_words": _count_words(text),
            "target_words": target_words,
            "external_links": count_external_links(text),
        },
    )
