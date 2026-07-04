"""T-7 (доделка): восстановление осиротевших прогонов."""

from __future__ import annotations

import os
import uuid

import fakeredis
import pytest

from app.orchestrator.recovery import get_active_article_ids


# --- парсинг активных задач (без БД/брокера) ---
class _FakeInspect:
    def __init__(self, raise_it=False):
        self._raise = raise_it

    def active(self):
        if self._raise:
            raise RuntimeError("broker down")
        return {"w1": [{"name": "run_pipeline", "args": ["ID1"]}]}

    def reserved(self):
        return {}

    def scheduled(self):
        return {"w1": [{"request": {"name": "run_pipeline", "args": ["ID2"]}}]}


class _FakeApp:
    def __init__(self, raise_it=False):
        self._raise = raise_it

        class _Control:
            def inspect(_self, timeout=2.0):
                return _FakeInspect(raise_it=raise_it)

        self.control = _Control()


def test_get_active_article_ids_parses_all_buckets():
    assert get_active_article_ids(_FakeApp()) == {"ID1", "ID2"}


def test_get_active_article_ids_none_on_broker_error():
    assert get_active_article_ids(_FakeApp(raise_it=True)) is None


# --- восстановление в БД (guarded) ---
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL не задан"
)


@pytestmark_db
def test_recover_marks_orphans_failed_and_protects_active():
    from sqlalchemy import text

    from app.db.enums import ArticleStatus
    from app.db.models import Article, PipelineStep, Site
    from app.db.session import SessionLocal, engine
    from app.orchestrator.recovery import recover_orphaned_pipelines

    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"БД недоступна: {e}")

    orphan = uuid.uuid4()
    active = uuid.uuid4()
    done = uuid.uuid4()

    def mk(aid, status):
        return Article(
            article_id=aid,
            site_domain="example.net",
            language="ru",
            status=status,
        )

    with SessionLocal() as s:
        if s.get(Site, "example.net") is None:
            s.add(Site(domain="example.net", name="Example"))
            s.commit()
        s.add_all(
            [
                mk(orphan, ArticleStatus.OUTLINE_DONE.value),  # нетерминальный «зависший»
                mk(active, ArticleStatus.SECTIONS_IN_PROGRESS.value),  # но «активный»
                mk(done, ArticleStatus.COMPLETED.value),  # терминальный
            ]
        )
        s.commit()

    try:
        r = fakeredis.FakeStrictRedis(decode_responses=True)
        recovered = recover_orphaned_pipelines(
            SessionLocal, {str(active)}, redis_client=r
        )
        assert str(orphan) in recovered
        assert str(active) not in recovered  # защищён (в active_ids)
        assert str(done) not in recovered

        with SessionLocal() as s:
            assert s.get(Article, orphan).status == ArticleStatus.FAILED.value
            assert s.get(Article, orphan).finished_at is not None
            assert s.get(Article, active).status == ArticleStatus.SECTIONS_IN_PROGRESS.value
            assert s.get(Article, done).status == ArticleStatus.COMPLETED.value
            steps = (
                s.query(PipelineStep)
                .filter(PipelineStep.article_id == orphan)
                .all()
            )
            assert any(
                st.step_name == "orphan_recovery" and st.error_message
                for st in steps
            )

        # событие aborted попало в durable-list осиротевшего прогона
        import json

        from app.orchestrator.events import events_list_key

        evts = [json.loads(x) for x in r.lrange(events_list_key(str(orphan)), 0, -1)]
        assert any(
            e["type"] == "aborted" and e["data"].get("reason") for e in evts
        )
    finally:
        with SessionLocal() as s:
            for aid in (orphan, active, done):
                a = s.get(Article, aid)
                if a:
                    s.delete(a)
            s.commit()
