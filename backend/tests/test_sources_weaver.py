"""T-9: sources_weaver — diff-проверка, ≤1 ссылка/секция, живость URL."""

from __future__ import annotations

import json

from app.agents.sources_weaver import (
    enforce_one_link_per_section,
    extract_links,
    text_preserved,
    weave_sources,
    unwrap_links,
)
from app.llm import MockLLMClient

ORIGINAL = (
    "# Байкал\n\n"
    "## География\nБайкал имеет глубину 1642 м и расположен в Сибири.\n\n"
    "## История\nОзеро существует около 25 млн лет.\n"
)


class _AI:
    main_keyword = "байкал"
    language = "ru"


def test_text_preserved_true_when_only_links_added():
    woven = ORIGINAL.replace("1642 м", "[1642 м](http://ex.com/depth)")
    assert text_preserved(ORIGINAL, woven)


def test_text_preserved_false_when_words_changed():
    woven = ORIGINAL.replace("1642 м", "[1500 м](http://ex.com/depth)")
    assert not text_preserved(ORIGINAL, woven)


def test_unwrap_ignores_images():
    md = "![alt](http://img/1.jpg) и [текст](http://ex.com)"
    assert unwrap_links(md) == "![alt](http://img/1.jpg) и текст"


def test_enforce_one_link_per_section():
    md = "## A\n[a](http://u1) и [b](http://u2)\n\n## B\n[c](http://u3)"
    out = enforce_one_link_per_section(md)
    assert extract_links(out) == [("a", "http://u1"), ("c", "http://u3")]


def test_weave_applies_and_enforces():
    woven = (
        "# Байкал\n\n"
        "## География\nБайкал имеет глубину [1642 м](http://ex.com/depth) и расположен в [Сибири](http://ex.com/sib).\n\n"
        "## История\nОзеро существует около [25 млн лет](http://ex.com/age).\n"
    )
    llm = MockLLMClient(responses={"sources_weaver_agent": json.dumps({"article_markdown": woven})})
    res = weave_sources(ORIGINAL, _AI(), [{"title": "Ex", "url": "http://ex.com"}], llm, url_alive=lambda u: True)
    assert res.applied
    # ≤1 ссылка на секцию: в «География» было 2 → осталась 1
    for section_links in _links_by_section(res.markdown):
        assert section_links <= 1


def test_weave_rejects_text_change():
    bad = ORIGINAL.replace("1642 м", "[1500 м](http://ex.com/depth)")
    llm = MockLLMClient(responses={"sources_weaver_agent": json.dumps({"article_markdown": bad})})
    res = weave_sources(ORIGINAL, _AI(), [], llm, url_alive=lambda u: True)
    assert not res.applied
    assert res.markdown == ORIGINAL


def test_weave_removes_dead_url():
    woven = ORIGINAL.replace("1642 м", "[1642 м](http://dead.example/x)")
    llm = MockLLMClient(responses={"sources_weaver_agent": json.dumps({"article_markdown": woven})})
    res = weave_sources(ORIGINAL, _AI(), [], llm, url_alive=lambda u: False)
    assert "http://dead.example/x" not in res.markdown
    assert "1642 м" in res.markdown  # текст остался, ссылка убрана


def _links_by_section(md):
    counts = []
    cur = 0
    for line in md.split("\n"):
        if line.startswith("#"):
            counts.append(cur)
            cur = 0
        else:
            cur += len(extract_links(line))
    counts.append(cur)
    return counts
