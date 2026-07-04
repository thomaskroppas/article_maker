#!/usr/bin/env python
"""Dev CLI для ручной проверки пайплайна до появления REST/UI (T-11+).

Запускать ВНУТРИ контейнера backend:
    docker compose exec backend python scripts/dev_pipeline.py <команда> ...

Команды:
    run [--no-review]      создать статью (готовый ArticleInput) и поставить в
                           очередь Celery; печатает article_id.
    events <id> [--follow] прочитать историю событий из pipeline:events:{id}.
    resume <id>            подтвердить ревью с ИЗМЕНЁННЫМ outline (меняет h1).
    stop <id>              послать stop-сигнал (увидите статус stopped_by_user).
    status <id>            показать статус статьи из БД.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

# /app в sys.path (скрипт лежит в /app/scripts)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.orchestrator.control import PipelineControl  # noqa: E402
from app.orchestrator.events import events_list_key  # noqa: E402


def _redis():
    import redis as redis_lib

    return redis_lib.Redis.from_url(get_settings().redis_url, decode_responses=True)


def _test_article_input(review: bool):
    from app.schemas import ArticleInput

    serp = os.environ.get("DEV_SERP_JSON", "/app/fixtures/serp_bundle_example.json")
    return ArticleInput.model_validate(
        dict(
            article_title="Где находится озеро Байкал",
            main_keyword="байкал где находится",
            secondary_keywords=["байкал дно", "где находится байкал", "глубина байкала"],
            language="ru",
            geo="ru",
            intent="informational",
            article_type="informational",
            difficulty="easy",
            style_archetype="expert_clear",
            required_elements=["faq", "quick_answer", "conclusion"],
            review_outline=review,
            serp_json_path=serp,
        )
    )


def cmd_run(args):
    from app.db.models import Article, Site
    from app.db.session import SessionLocal
    from app.db.enums import ArticleStatus
    from app.worker import run_pipeline

    ai = _test_article_input(review=not args.no_review)
    aid = uuid.UUID(ai.article_id)

    with SessionLocal() as s:
        if s.get(Site, "example.net") is None:
            s.add(Site(domain="example.net", name="Example"))
            s.commit()
        s.add(
            Article(
                article_id=aid,
                site_domain="example.net",
                language=ai.language,
                title=ai.article_title,
                main_keyword=ai.main_keyword,
                status=ArticleStatus.CREATED.value,
                input_data=ai.model_dump(mode="json"),
            )
        )
        s.commit()

    run_pipeline.delay(str(aid))
    print(f"article_id = {aid}")
    print(f"review_outline = {ai.review_outline}")
    print("Дальше:")
    print(f"  события:  python scripts/dev_pipeline.py events {aid} --follow")
    if ai.review_outline:
        print(f"  resume:   python scripts/dev_pipeline.py resume {aid}")
        print(f"  stop:     python scripts/dev_pipeline.py stop {aid}")
    print(f"  статус:   python scripts/dev_pipeline.py status {aid}")


def _print_event(evt: dict):
    data = evt.get("data", {})
    if evt["type"] == "log_entry":
        summary = f"[{data.get('level')}] {data.get('message')}"
    elif evt["type"] in ("step_started", "step_finished"):
        summary = f"{data.get('step_name')} (шаг {data.get('step_number', '')})"
    elif evt["type"] == "cost_update":
        summary = f"article=${data.get('article')} session=${data.get('session')}"
    elif evt["type"] == "review_ready":
        summary = f"outline.h1='{data.get('outline', {}).get('h1')}'"
    elif evt["type"] == "aborted":
        summary = f"reason={data.get('reason')}"
    else:
        summary = json.dumps(data, ensure_ascii=False)[:120]
    print(f"#{evt['event_id']:>3} {evt['type']:<15} {summary}")


def cmd_events(args):
    r = _redis()
    key = events_list_key(args.article_id)
    seen = 0
    while True:
        raw = r.lrange(key, seen, -1)
        for item in raw:
            _print_event(json.loads(item))
        seen += len(raw)
        if not args.follow:
            break
        time.sleep(0.5)


def cmd_resume(args):
    r = _redis()
    key = events_list_key(args.article_id)
    review = None
    for item in r.lrange(key, 0, -1):
        evt = json.loads(item)
        if evt["type"] == "review_ready":
            review = evt["data"]["outline"]
    if review is None:
        print("Событие review_ready ещё не пришло — подождите паузы ревью.")
        return
    review = dict(review)
    review["h1"] = "[EDITED] " + review.get("h1", "")
    subs = PipelineControl(r, args.article_id).confirm_review({"outline": review})
    print(f"resume отправлен, изменён h1 → '{review['h1']}', подписчиков: {subs}")
    if subs == 0:
        print("ВНИМАНИЕ: 0 подписчиков — воркер ещё не на паузе или уже прошёл её.")


def cmd_stop(args):
    PipelineControl(_redis(), args.article_id).request_stop()
    print(f"stop-сигнал отправлен для {args.article_id}")


def cmd_status(args):
    from app.db.models import Article
    from app.db.session import SessionLocal

    with SessionLocal() as s:
        a = s.get(Article, uuid.UUID(args.article_id))
        if a is None:
            print("Статья не найдена")
            return
        print(f"status      = {a.status}")
        print(f"started_at  = {a.started_at}")
        print(f"finished_at = {a.finished_at}")


def main():
    p = argparse.ArgumentParser(description="Dev CLI пайплайна")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="создать статью и поставить в очередь")
    r.add_argument("--no-review", action="store_true", help="без паузы ревью")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("events", help="история событий")
    e.add_argument("article_id")
    e.add_argument("--follow", action="store_true")
    e.set_defaults(func=cmd_events)

    rs = sub.add_parser("resume", help="resume с изменённым outline")
    rs.add_argument("article_id")
    rs.set_defaults(func=cmd_resume)

    st = sub.add_parser("stop", help="stop-сигнал")
    st.add_argument("article_id")
    st.set_defaults(func=cmd_stop)

    ss = sub.add_parser("status", help="статус статьи")
    ss.add_argument("article_id")
    ss.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
