"""Верификация утверждений через Wikipedia/Wikidata — ТЗ §9.4.2–9.4.4.

Никогда не бросает исключение: при любой ошибке — status='uncertain' (§9.4.3).
lookup_fn инъектируется (в тестах — фейк; по умолчанию — Wikipedia REST).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Optional

from ..schemas import FactCheckReport, FactCheckResult, FactStatement
from .cache import WikiCache

_NUM_RE = re.compile(r"-?\d[\d\s.,]*")


def _extract_number(text: str) -> Optional[float]:
    if not text:
        return None
    m = _NUM_RE.search(text)
    if not m:
        return None
    raw = m.group(0).strip().replace(" ", "").replace(" ", "")
    # 1.642 (тыс.) vs 1,642 — берём последнюю группу как дробную, если 1-2 цифры
    raw = raw.replace(",", ".")
    if raw.count(".") > 1:
        parts = raw.split(".")
        raw = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(raw)
    except ValueError:
        return None


def compare_numeric(article_value: str, external_value, tol: float = 0.05) -> bool:
    a = _extract_number(str(article_value))
    e = external_value if isinstance(external_value, (int, float)) else _extract_number(str(external_value))
    if a is None or e is None or e == 0:
        return False
    return abs(a - e) / abs(e) <= tol


def _contains(haystack, needle: str) -> bool:
    if not haystack or not needle:
        return False
    return needle.lower() in str(haystack).lower()


def _judge(stmt: FactStatement, ext: Optional[dict]) -> FactCheckResult:
    if not ext:
        return FactCheckResult(statement=stmt, status="uncertain", confidence=0.3)

    value = ext.get("value")
    common = dict(
        external_value=str(value)[:300] if value is not None else None,
        source_url=ext.get("source_url"),
        source_name=ext.get("source_name"),
    )

    if stmt.type in ("numeric", "date"):
        external_num = ext.get("numeric_value")
        if external_num is None:
            external_num = _extract_number(str(value))
        art_num = _extract_number(stmt.value_in_article)
        if art_num is not None and external_num is not None:
            ok = compare_numeric(stmt.value_in_article, external_num)
            return FactCheckResult(
                statement=stmt, status="verified" if ok else "mismatch",
                confidence=0.85 if ok else 0.8, **common
            )
        # число не сопоставить → без наказания (§22.13): verified при упоминании, иначе uncertain
        ok = _contains(value, stmt.value_in_article)
        return FactCheckResult(
            statement=stmt, status="verified" if ok else "uncertain",
            confidence=0.6 if ok else 0.4, **common
        )

    ok = _contains(value, stmt.value_in_article) or _contains(value, stmt.subject)
    return FactCheckResult(
        statement=stmt, status="verified" if ok else "uncertain",
        confidence=0.6 if ok else 0.4, **common
    )


def default_lookup(
    statement: FactStatement, language: str, http_get: Optional[Callable] = None
) -> Optional[dict]:
    """Wikipedia REST summary по subject (§9.4.3 fallback). Никогда не бросает."""
    if http_get is None:
        import requests

        http_get = lambda url, timeout=10: requests.get(url, timeout=timeout)  # noqa: E731
    title = statement.subject.strip().replace(" ", "_")
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        resp = http_get(url, timeout=10)
        if getattr(resp, "status_code", 200) != 200:
            return None
        data = resp.json()
        return {
            "value": data.get("extract", ""),
            "source_url": data.get("content_urls", {}).get("desktop", {}).get("page", url),
            "source_name": f"Wikipedia ({language})",
        }
    except Exception:  # noqa: BLE001
        return None


def verify_statements(
    statements: list[FactStatement],
    language: str,
    *,
    lookup_fn: Optional[Callable] = None,
    cache: Optional[WikiCache] = None,
) -> FactCheckReport:
    lookup = lookup_fn or default_lookup
    results: list[FactCheckResult] = []
    for stmt in statements:
        key = f"{language}|{stmt.subject}|{stmt.property}|{stmt.type}"
        ext = cache.get("verify", key) if cache else None
        if ext is None:
            try:
                ext = lookup(stmt, language)
            except Exception:  # noqa: BLE001 — §9.4.3: не поднимать исключение
                ext = None
            if cache is not None:
                cache.set("verify", key, ext)
        results.append(_judge(stmt, ext))

    return FactCheckReport(
        total_statements=len(results),
        verified=sum(r.status == "verified" for r in results),
        mismatches=sum(r.status == "mismatch" for r in results),
        uncertain=sum(r.status == "uncertain" for r in results),
        results=results,
        checked_at=datetime.now(timezone.utc),
    )
