"""T-9: fact_checker — извлечение (из article.md на моке) + верификация с кэшем."""

from __future__ import annotations

import json

from app.factcheck import WikiCache, compare_numeric, verify_statements
from app.factcheck.extraction import FactExtractionAgent
from app.llm import MockLLMClient
from app.paths import reference_dir
from app.schemas import FactStatement

# 7 утверждений — имитация ответа extraction-агента.
EXTRACTION_RESPONSE = json.dumps(
    {
        "statements": [
            {"text": "Глубина Байкала 1642 м.", "type": "numeric", "subject": "Байкал", "property": "глубина", "value_in_article": "1642 м"},
            {"text": "Байкал существует около 25 млн лет.", "type": "numeric", "subject": "Байкал", "property": "возраст", "value_in_article": "25 млн лет"},
            {"text": "Байкал находится в Сибири.", "type": "location", "subject": "Байкал", "property": None, "value_in_article": "Сибирь"},
            {"text": "Площадь Байкала 31722 км².", "type": "numeric", "subject": "Байкал", "property": "площадь", "value_in_article": "31722 км²"},
            {"text": "Байкал в Иркутской области.", "type": "location", "subject": "Байкал", "property": None, "value_in_article": "Иркутская область"},
            {"text": "Байкал — объект ЮНЕСКО.", "type": "name", "subject": "ЮНЕСКО", "property": None, "value_in_article": "ЮНЕСКО"},
            {"text": "Байкал замерзает в январе.", "type": "date", "subject": "Байкал", "property": "ледостав", "value_in_article": "январь"},
        ]
    }
)


class _AI:
    language = "ru"


def test_extraction_from_article_md_5_to_20():
    article_md = (reference_dir() / "article.md").read_text(encoding="utf-8")
    agent = FactExtractionAgent(MockLLMClient(responses={"fact_checker_agent": EXTRACTION_RESPONSE}))
    statements = agent.run(article_md, "ru")
    assert 5 <= len(statements) <= 20
    assert all(isinstance(s, FactStatement) for s in statements)
    assert all(s.type in ("numeric", "date", "location", "name") for s in statements)


def test_extraction_clamps_to_20():
    many = {"statements": [
        {"text": f"f{i}", "type": "name", "subject": f"s{i}", "value_in_article": f"v{i}"}
        for i in range(30)
    ]}
    agent = FactExtractionAgent(MockLLMClient(responses={"fact_checker_agent": json.dumps(many)}))
    assert len(agent.run("md", "ru")) == 20


def test_compare_numeric_tolerance():
    assert compare_numeric("1642 м", 1642)
    assert compare_numeric("1640 м", 1642)  # в пределах 5%
    assert not compare_numeric("1500 м", 1642)


def _stmt(**kw):
    base = dict(text="t", type="numeric", subject="Байкал", property="глубина", value_in_article="1642 м")
    base.update(kw)
    return FactStatement.model_validate(base)


def test_verify_verified_mismatch_uncertain():
    statements = [
        _stmt(value_in_article="1642 м"),  # verified
        _stmt(value_in_article="1500 м"),  # mismatch
        _stmt(type="name", subject="НечтоНесуществующее", value_in_article="x"),  # uncertain
    ]

    def lookup(stmt, lang):
        if stmt.subject == "Байкал":
            return {"value": "Озеро Байкал", "numeric_value": 1642,
                    "source_url": "http://wiki/baikal", "source_name": "Wikidata"}
        return None  # не нашли сущность → uncertain

    report = verify_statements(statements, "ru", lookup_fn=lookup)
    assert report.total_statements == 3
    assert report.verified == 1
    assert report.mismatches == 1
    assert report.uncertain == 1


def test_verify_uses_cache(tmp_path):
    calls = {"n": 0}

    def lookup(stmt, lang):
        calls["n"] += 1
        return {"value": "x", "numeric_value": 1642, "source_url": "u", "source_name": "Wikidata"}

    cache = WikiCache(tmp_path)
    st = [_stmt()]
    verify_statements(st, "ru", lookup_fn=lookup, cache=cache)
    verify_statements(st, "ru", lookup_fn=lookup, cache=cache)  # второй раз — из кэша
    assert calls["n"] == 1


def test_verify_never_raises_on_lookup_error():
    def lookup(stmt, lang):
        raise RuntimeError("network down")

    report = verify_statements([_stmt()], "ru", lookup_fn=lookup)
    assert report.uncertain == 1  # ошибка → uncertain, не исключение
