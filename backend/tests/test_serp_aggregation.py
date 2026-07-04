"""T-5: усечённое среднее и fallback по числу конкурентов (ТЗ §6.4), N=0/2/4/7."""

from __future__ import annotations

from app.serp.aggregation import robust_average, trimmed_mean


def test_trimmed_mean_drops_min_and_max():
    # [10,20,30,40,1000] → без 10 и 1000 → mean(20,30,40)=30
    assert trimmed_mean([10, 20, 30, 40, 1000]) == 30.0


def test_n7_uses_trimmed_mean():
    r = robust_average([10, 20, 30, 40, 50, 60, 5000])
    assert r.method == "trimmed_mean"
    assert r.warning is None
    # без 10 и 5000 → mean(20,30,40,50,60)=40
    assert r.avg == 40.0


def test_n4_uses_median():
    r = robust_average([10, 20, 30, 100])
    assert r.method == "median"
    assert r.avg == 25.0  # median(10,20,30,100)


def test_n2_uses_mean_with_warning():
    r = robust_average([10, 40])
    assert r.method == "mean"
    assert r.avg == 25.0
    assert r.warning


def test_n0_returns_none_method():
    r = robust_average([])
    assert r.method == "none"
    assert r.avg == 0.0
    assert r.warning
