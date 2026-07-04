"""T-2: юнит-тесты централизованного слоя legacy-нормализации."""

from __future__ import annotations

from app.schemas import legacy_compat as lc


def test_required_elements_sources_block_to_weaved():
    assert lc.normalize_required_elements(["sources_block", "faq"]) == [
        "weaved_sources",
        "faq",
    ]


def test_required_elements_dedup_and_strip():
    assert lc.normalize_required_elements(["faq", " faq ", "", "list"]) == [
        "faq",
        "list",
    ]


def test_string_list_dedup():
    assert lc.normalize_string_list(["a", "a", " b ", ""]) == ["a", "b"]


def test_word_count_range_avg_alias():
    assert lc.normalize_word_count_range({"min": 1, "avg": 5})["avg_trimmed"] == 5


def test_word_count_range_keeps_explicit_avg_trimmed():
    out = lc.normalize_word_count_range({"avg": 5, "avg_trimmed": 7})
    assert out["avg_trimmed"] == 7  # явный §13-ключ не перетирается legacy


def test_data_sensitivity_alias():
    assert lc.normalize_data_sensitivity({"time_sensitive": True})[
        "has_volatile_data"
    ] is True


def test_qa_warnings_list_to_object():
    out = lc.normalize_qa_warnings(["a", "b"])
    assert out == {"critical": [], "medium": ["a", "b"], "minor": []}


def test_qa_warnings_object_passthrough():
    obj = {"critical": ["x"], "medium": [], "minor": []}
    assert lc.normalize_qa_warnings(obj) is obj
