# DEV_RUNBOOK — ручная проверка пайплайна до REST/UI

Временный runbook на период до появления REST API (T-11) и UI (T-13). Использует
`backend/scripts/dev_pipeline.py` внутри контейнера backend. Всё на MockLLM —
живых LLM-вызовов нет (до T-14).

## 0. Поднять стек

```bash
git pull
docker compose up -d --build
docker compose ps            # все сервисы Up; backend/worker/postgres/redis — (healthy)
```

Хостовые порты по умолчанию: API **8010**, фронт **3010**, postgres **5433**,
redis **6380** (переопределяются в `.env`: `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT`,
`POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`).

## 1. Миграции

```bash
docker compose exec backend alembic upgrade head
```

## 2. Запустить пайплайн (MockLLM, с паузой ревью)

```bash
docker compose exec backend python scripts/dev_pipeline.py run
# → article_id = <ID>
```

## 3. Смотреть события (чтение pipeline:events:{id})

```bash
docker compose exec backend python scripts/dev_pipeline.py events <ID> --follow
# останавливается на review_ready; Ctrl-C — чистый выход
```

## 4. Resume с изменённым outline

```bash
docker compose exec backend python scripts/dev_pipeline.py resume <ID>
docker compose exec backend python scripts/dev_pipeline.py status <ID>   # → sections_in_progress
```

## 5. Stop → stopped_by_user

```bash
docker compose exec backend python scripts/dev_pipeline.py run           # → NEW_ID
# дождитесь review_ready в events, затем:
docker compose exec backend python scripts/dev_pipeline.py stop <NEW_ID>
docker compose exec backend python scripts/dev_pipeline.py status <NEW_ID>  # → stopped_by_user
```

## 6. Таймаут ревью (быстро, через env)

ВАЖНО: используйте `printf` с переводом строки, иначе переменная приклеится к
последней строке `.env`:

```bash
printf '\nREVIEW_TIMEOUT_SECONDS=15\n' >> .env
docker compose up -d worker            # воркер перечитает env
docker compose exec backend python scripts/dev_pipeline.py run   # → TID, resume НЕ делать
sleep 16
docker compose exec backend python scripts/dev_pipeline.py status <TID>  # → review_timeout
```

После проверки уберите строку из `.env` и `docker compose up -d worker`.
`REVIEW_TIMEOUT_SECONDS` — только для проверки; боевой дефолт `REVIEW_TIMEOUT_HOURS=4`.

## 7. Осиротевшие прогоны (после рестарта/падения воркера)

Если воркер пересоздан во время паузы ревью, его задача гибнет, а статья
осталась бы в нетерминальном статусе. Восстановление запускается автоматически
при старте воркера (переводит такие статьи в `failed`). Вручную:

```bash
docker compose exec backend python scripts/dev_pipeline.py recover
# → список переведённых в failed (или «Осиротевших прогонов не найдено»)
```
