"""T-6: юнит-тесты агентов шагов 2–5 (без сети, MockLLM/чистые функции)."""

from __future__ import annotations

from app.agents import (
    AgentCache,
    build_data_handling_rules,
    compute_ranges,
    compute_target_word_count,
    extract_json,
    filter_content_gaps,
)
from app.agents.brief import MULTIPLIERS
from app.schemas import (
    ContentGap,
    DataSensitivity,
    HeadingsData,
    PageData,
    SerpBundle,
)


# --- json_parse ---
def test_extract_json_raw():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_embedded_text():
    assert extract_json('Вот результат:\n{"a": [1,2]}\nготово') == {"a": [1, 2]}


def test_extract_json_list():
    assert extract_json('["x", "y"]') == ["x", "y"]


def test_extract_json_invalid():
    assert extract_json("нет json") is None


# --- agent cache ---
def test_agent_cache_key_sorts_secondary():
    k1 = AgentCache.make_key("brief_agent", "T", "kw", ["b", "a"])
    k2 = AgentCache.make_key("brief_agent", "T", "kw", ["a", "b"])
    assert k1 == k2
    assert k1 == "brief_agent:t:kw:a,b"


def test_agent_cache_roundtrip(tmp_path):
    c = AgentCache(tmp_path)
    assert c.get("brief_agent", "T", "kw", ["a"]) is None
    c.set("brief_agent", "T", "kw", ["a"], {"goal": "x"})
    assert c.get("brief_agent", "T", "kw", ["a"]) == {"goal": "x"}


# --- competitor ranges (§6.4) ---
def _bundle_with_wcs(wcs, h2_counts):
    pages = [
        PageData(
            url=f"http://u{i}",
            word_count=wc,
            headings=HeadingsData(h2=[f"h{j}" for j in range(h2)]),
        )
        for i, (wc, h2) in enumerate(zip(wcs, h2_counts))
    ]
    return SerpBundle(query="q", geo="ru", language="ru", pages=pages)


def test_compute_ranges_trimmed_for_n7():
    b = _bundle_with_wcs([10, 20, 30, 40, 50, 60, 5000], [1, 2, 3, 4, 5, 6, 7])
    wc, h2, warns = compute_ranges(b)
    assert wc.per_page == [10, 20, 30, 40, 50, 60, 5000]
    assert wc.min == 10 and wc.max == 5000
    assert wc.avg_trimmed == 40.0  # без 10 и 5000
    assert warns == []


def test_compute_ranges_low_sample_warning():
    b = _bundle_with_wcs([100, 200], [1, 2])
    _, _, warns = compute_ranges(b)
    assert warns  # N=2 → warning


# --- brief calc (§6.6, §7.3.3) ---
class _AI:
    length_strategy = "match_top"
    target_word_count = None


def _report_with_avg(avg, volatile=False):
    from app.schemas import CompetitorAnalysisReport, WordCountRange

    return CompetitorAnalysisReport(
        word_count_range=WordCountRange(avg_trimmed=avg),
        h2_count_range=WordCountRange(),
        common_h2_titles=[],
        must_have_topics=[],
        optional_topics=[],
        content_gaps=[],
        data_sensitivity=DataSensitivity(has_volatile_data=volatile),
    )


def test_target_word_count_match_top():
    ai = _AI()
    assert compute_target_word_count(ai, _report_with_avg(1000)) == 1000


def test_target_word_count_multipliers():
    ai = _AI()
    for strat, mult in MULTIPLIERS.items():
        ai.length_strategy = strat
        assert compute_target_word_count(ai, _report_with_avg(1000)) == round(1000 * mult)


def test_target_word_count_custom():
    ai = _AI()
    ai.length_strategy = "custom"
    ai.target_word_count = 777
    assert compute_target_word_count(ai, _report_with_avg(1000)) == 777


def test_data_handling_rules_volatile():
    r = build_data_handling_rules(DataSensitivity(has_volatile_data=True))
    assert r.avoid_exact_dates and r.use_approximate_language


def test_data_handling_rules_stable():
    r = build_data_handling_rules(DataSensitivity(has_volatile_data=False))
    assert not r.avoid_exact_dates and not r.use_approximate_language


# --- FR-18 dedup ---
def test_filter_content_gaps():
    gaps = [
        ContentGap(title="Глубина озера", description="d"),
        ContentGap(title="История", description="d"),
    ]
    out = filter_content_gaps(gaps, ["глубина  озера", "Климат"])
    assert [g.title for g in out] == ["История"]
