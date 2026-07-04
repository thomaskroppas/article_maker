"""T-3: живые Alembic-миграции против реального Postgres.

Пропускается, если DATABASE_URL не задан или БД недоступна (напр. локальный
`pytest` без поднятой БД). В docker (`docker compose exec backend pytest`) БД
доступна и тест выполняется.

Полный roundtrip downgrade→upgrade разрушает данные, поэтому включается только
флагом SEO_DB_DESTRUCTIVE_TESTS=1.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_URL = os.environ.get("DATABASE_URL")


def _engine_or_skip():
    if not DB_URL:
        pytest.skip("DATABASE_URL не задан — live-миграции пропущены")
    try:
        eng = create_engine(DB_URL)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return eng
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"БД недоступна: {e}")


def _alembic_cfg():
    from alembic.config import Config

    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    return cfg


def _counts(eng):
    with eng.connect() as c:
        return {
            "niches": c.execute(text("SELECT count(*) FROM niches")).scalar(),
            "archetypes": c.execute(text("SELECT count(*) FROM archetypes")).scalar(),
            "vector": c.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname='vector'")
            ).scalar(),
            "mv": c.execute(
                text(
                    "SELECT count(*) FROM pg_matviews "
                    "WHERE matviewname='mv_articles_by_site_month'"
                )
            ).scalar(),
        }


def test_upgrade_head_creates_schema_and_seed():
    eng = _engine_or_skip()
    from alembic import command

    command.upgrade(_alembic_cfg(), "head")
    c = _counts(eng)
    assert c["niches"] == 7
    assert c["archetypes"] == 36
    assert c["vector"] == 1, "расширение vector не создано"
    assert c["mv"] == 1, "материализованный view не создан"


def test_downgrade_upgrade_roundtrip():
    if os.environ.get("SEO_DB_DESTRUCTIVE_TESTS") != "1":
        pytest.skip("разрушающий тест выключен (SEO_DB_DESTRUCTIVE_TESTS=1 для запуска)")
    eng = _engine_or_skip()
    from alembic import command

    cfg = _alembic_cfg()
    command.downgrade(cfg, "base")
    with eng.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        ).scalar()
    assert n == 1, "после downgrade base осталась только alembic_version"
    command.upgrade(cfg, "head")
    assert _counts(eng)["niches"] == 7
