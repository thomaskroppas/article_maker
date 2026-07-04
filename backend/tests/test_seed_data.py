"""T-3: целостность seed-данных (без БД).

Импортируем константы миграции 0002 и проверяем инварианты.
"""

from __future__ import annotations

import importlib.util
import os

_MIG = os.path.join(
    os.path.dirname(__file__),
    "..",
    "alembic",
    "versions",
    "0002_seed_niches_archetypes.py",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("seed_0002", os.path.abspath(_MIG))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mig = _load_migration()


def test_seven_niches():
    assert len(mig.NICHES) == 7
    ids = [n[0] for n in mig.NICHES]
    assert ids == sorted(set(ids), key=ids.index)  # без дублей
    assert set(ids) == {"travel", "home", "auto", "lifestyle", "pets", "garden", "utility"}


def test_at_least_30_archetypes():
    assert len(mig.ARCHETYPES) >= 30


def test_archetype_ids_unique():
    ids = [a[0] for a in mig.ARCHETYPES]
    assert len(ids) == len(set(ids))


def test_archetype_niche_ids_valid():
    niche_ids = {n[0] for n in mig.NICHES}
    for a in mig.ARCHETYPES:
        assert a[1] in niche_ids, f"архетип {a[0]} ссылается на неизвестную нишу {a[1]}"


def test_archetype_intent_triggers_valid():
    allowed = {"informational", "how_to"}
    for a in mig.ARCHETYPES:
        assert a[4], f"{a[0]}: пустые intent_triggers"
        assert set(a[4]) <= allowed, f"{a[0]}: недопустимый intent {a[4]}"
