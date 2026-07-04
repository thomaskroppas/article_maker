"""T-2: выходной контракт пайплайна — строго ТЗ раздел 13.

Требование заказчика (c): новая генерация НЕ должна писать legacy desktop-поля.
Даже если на вход пришёл legacy-формат, после нормализации model_dump() содержит
только поля §13 (никаких avg / sources_block / time_sensitive / warnings-списком).
"""

from __future__ import annotations

from app import schemas


def _valid_article_input(**over):
    base = dict(
        article_title="Заголовок статьи",
        main_keyword="ключ",
        secondary_keywords=["один"],
        language="ru",
        geo="Россия",
        intent="informational",
        article_type="informational",
        difficulty="easy",
        style_archetype="expert_clear",
        required_elements=["faq"],
    )
    base.update(over)
    return base


def test_article_input_sources_block_normalized_out():
    ai = schemas.ArticleInput.model_validate(
        _valid_article_input(required_elements=["sources_block", "faq"])
    )
    dumped = ai.model_dump()
    assert "sources_block" not in dumped["required_elements"]
    assert "weaved_sources" in dumped["required_elements"]


def test_word_count_range_avg_not_in_output():
    wcr = schemas.WordCountRange.model_validate({"min": 1, "avg": 5.0, "max": 9})
    dumped = wcr.model_dump()
    assert dumped["avg_trimmed"] == 5.0
    assert "avg" not in dumped  # legacy-поле в выход не попадает


def test_data_sensitivity_legacy_keys_not_in_output():
    ds = schemas.DataSensitivity.model_validate(
        {"time_sensitive": True, "avoid_exact_dates": True}
    )
    dumped = ds.model_dump()
    assert dumped["has_volatile_data"] is True
    assert "time_sensitive" not in dumped
    assert "avoid_exact_dates" not in dumped
    assert set(dumped) == {"has_volatile_data", "has_precise_numbers", "notes"}


def test_qa_warnings_object_not_list_in_output():
    qa = schemas.QAResult.model_validate(
        {
            "status": "pass",
            "score": 89,
            "criteria_scores": {},
            "warnings": ["w1", "w2"],  # legacy плоский список
            "fail_reasons": [],
            "recommendation": "ok",
        }
    )
    dumped = qa.model_dump()
    assert isinstance(dumped["warnings"], dict)
    assert set(dumped["warnings"]) == {"critical", "medium", "minor"}
    assert dumped["warnings"]["medium"] == ["w1", "w2"]


def test_competitor_report_output_uses_avg_trimmed():
    # Легаси competitor с avg должен на выходе дать avg_trimmed, без avg.
    ca = schemas.CompetitorAnalysisReport.model_validate(
        {
            "word_count_range": {"min": 100, "avg": 500, "max": 900, "per_page": []},
            "h2_count_range": {"min": 3, "avg": 6, "max": 9, "per_page": []},
            "common_h2_titles": [],
            "must_have_topics": [],
            "optional_topics": [],
            "content_gaps": [],
        }
    )
    dumped = ca.model_dump()
    assert dumped["word_count_range"]["avg_trimmed"] == 500
    assert "avg" not in dumped["word_count_range"]
    assert "avg" not in dumped["h2_count_range"]
