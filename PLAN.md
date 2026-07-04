# PLAN.md — план работ SEO Pipeline

Задачи выполняются **строго по порядку, по одной**. Каждая заканчивается зелёными тестами и одним коммитом `T-NN: <суть>`. Выполненную задачу отмечай `[x]`. Разделы ТЗ указаны как обязательное чтение перед стартом задачи.

---

## Этап 1 — ядро (русский язык)

- [x] **T-0. Проверка окружения.**
  ТЗ: разделы 4, 19. Проверить: Docker 24+, тестовый запрос к SERP-провайдеру (serper.dev — основной; команда в CLAUDE.md, 1 кредит, один раз), наличие `env_with_keys.txt`. Скопировать его в `.env`, создать `.gitignore` (`.env`, `env_with_keys.txt`, `node_modules`, `__pycache__`, `data/`), `git init` + первый коммит.
  **DoD:** SERP-провайдер (serper.dev) отвечает JSON'ом (или заказчику отправлен блокер); репозиторий инициализирован.

- [ ] **T-1. Каркас и Docker Compose.**
  ТЗ: 4, 5, 19. Создать `backend/` (FastAPI, `/api/health`), `frontend/` (Vite + React, пустая оболочка с тёмной темой), `docker-compose.yml` (postgres `pgvector/pgvector:pg15`, redis:7, backend, worker-заглушка Celery, frontend; nginx под profile `production`), `env.example` без секретов.
  **DoD:** `docker compose up -d` поднимает всё; `GET /api/health` → 200; фронт открывается на :3000.

- [ ] **T-2. Pydantic-схемы + тесты на fixtures.**
  ТЗ: раздел 13 целиком. Реализовать все схемы (ArticleInput с валидаторами, SerpBundle, CompetitorAnalysisReport + DataSensitivity, Brief, Outline, SectionFinal, CriticFeedback, QAResult, FactStatement, FinalPackage и остальные).
  **DoD:** каждый файл из `fixtures/` и все JSON из `reference_article/` парсятся соответствующей схемой без ошибок; тесты это доказывают.

- [ ] **T-3. БД: модели, миграции, seed.**
  ТЗ: раздел 12, Приложение C (статусы), 10.10 (app_settings). SQLAlchemy-модели всех таблиц, Alembic-миграция №1 (структура + `CREATE EXTENSION vector`), миграция №2 — seed из `seed/seed_niches_archetypes.py` (7 ниш, 30+ архетипов). Enum статусов статьи по Приложению C.
  **DoD:** `alembic upgrade head` с нуля проходит; в БД 7 ниш и все архетипы; `downgrade` работает.

- [ ] **T-4. LLM-слой: клиент, загрузчик промптов, учёт стоимости, MockLLMClient.**
  ТЗ: 7.1, 7.2, 20.2–20.4, 6.2. Загрузка `prompts/<agent>/v1.txt` через `string.Template` (внимание: риск 22.8 — `$` в текстах), AGENT_PARAMS (модель/температура per-agent из 7.2), ретраи 429/500, подсчёт стоимости по токенам, сохранение промпта и ответа на диск. MockLLMClient отдаёт fixtures по имени агента.
  **DoD:** тест: рендер промпта каждого из 13 агентов на фиктивных переменных не падает; мок возвращает валидные схемы; стоимость считается.

- [ ] **T-5. Шаг 1 — SERP через интерфейс `SerpProvider`.**
  ТЗ: 6.3, 4.1, 14.2, 6.4 (fallback trimmed mean). Абстрактный `SerpProvider.fetch(query, geo, hl)` + три реализации: `SerperDevProvider` (основной, POST google.serper.dev/search, `X-API-KEY`, organic top-10; ключ `serper_api_key` из app_settings, БД → .env), `XmlstockProvider` (альтернатива, GET из `XMLSTOCK_API_URL`; недоступен без URL), `ManualProvider` (`serp_json_path` / `manual_sources`, логика без изменений). Выбор по настройке `serp_provider`; manual-режим включается автоматически при заданных ручных источниках. Кэш по хэшу (`...|provider`), парсинг readability-lxml, fallback усечённого среднего при N<5.
  **DoD:** тест на `fixtures/serp_bundle_example.json` через `serp_json_path`; юнит-тесты всех трёх провайдеров на моках (serper: разбор `organic`; xmlstock: разбор `items` + недоступность без URL; manual: json_path и manual_sources); тест выбора провайдера по `serp_provider` и авто-manual; юнит-тесты fallback для N=0/2/4/7; живые вызовы SERP-провайдеров в тестах запрещены.

- [ ] **T-6. Шаги 2–5 — competitor, LSI, brief, outline (+ кэш агентов).**
  ТЗ: 6.4–6.7, 7.3.2–7.3.4. Кэш с ключом из 6.2. brief_agent формирует `data_handling_rules` из `data_sensitivity` (логика в коде). Дедупликация content gaps (FR-18).
  **DoD:** пайплайн шагов 1–5 на MockLLM проходит end-to-end, выходы валидны схемами и совпадают по структуре с `reference_article/`.

- [ ] **T-7. Оркестратор Celery: статусы, события, ревью-пауза.**
  ТЗ: 6.1, 6.8, 6.8.1, 11.3, Приложение C. Celery-задача `run_pipeline`, статусы в БД, события в Redis pub/sub **и** в list `pipeline:events:{id}` (event_id — монотонный счётчик), пауза `review_outline` с таймаутом REVIEW_TIMEOUT_HOURS, stop-сигнал.
  **DoD:** интеграционный тест: запуск → пауза → resume с изменённым outline → продолжение; таймаут ревью завершает задачу статусом `review_timeout`; события читаются из list.

- [ ] **T-8. Шаги 6–9 — секции, сборка, картинки, FAQ.**
  ТЗ: 6.9–6.13, 7.3.5–7.3.7, раздел 8.2.5 (настройки картинок), FR-18 (дедуп FAQ). Цикл Writer→Critic→Editor (порог 60, флаг `enable_section_critic`), SUMMARY-маркеры, сборка markdown, image-агент (ключи + Pixabay/Unsplash с ротацией ключей при 429), FAQ с дедупликацией.
  **DoD:** на MockLLM собирается полный draft, структурно эквивалентный `reference_article/full_draft.json`; тест дедупа FAQ; тест ротации ключей картинок.

- [ ] **T-9. Новые промпты + шаги 10–11 — sources_weaver, fact_checker.**
  ТЗ: 3.13, 3.12, 7.3.9, 9 (fact-checking целиком), 20.5. Написать оба промпта по требованиям 20.2 (английский, Template, JSON-only), реализовать verification через Wikipedia/Wikidata с кэшем, проверку живости URL (HEAD, 5 сек).
  **DoD:** юнит-тесты: weaver не меняет текст вне ссылок (diff-проверка), ≤1 ссылка/секция; fact_checker извлекает 5–20 валидных FactStatement из `reference_article/article.md` (на моке); формат промптов проходит рендер T-4.

- [ ] **T-10. Шаги 12–13 — QA и метаданные.**
  ТЗ: 6.15, 6.16, 6.2.1 (пороги), 8.2 (pysbd, стоп-слова ru). 6 кодовых метрик + 3 LLM-метрики, правило-предохранитель factuality (>20% mismatches → максимум pass_with_warnings), проверка weaved_sources кодом, разделение warnings, metadata_agent.
  **DoD:** QA-метрики на `reference_article/article.md` дают score в пределах ±5 от `reference_article/qa_result.json`; юнит-тесты порогов и предохранителя.

- [ ] **T-11. REST API + basic auth + настройки.**
  ТЗ: 11.1–11.2, 10.10 (app_settings). Все endpoints 11.2, включая `GET /api/pipeline/{id}/events`, DELETE статьи с удалением папки, settings с Fernet-шифрованием и приоритетом БД → .env.
  **DoD:** тесты на каждый endpoint; ключи не возвращаются в GET /api/settings; смена ключа применяется без рестарта (worker читает из БД на старте задачи).

- [ ] **T-12. WebSocket + восстановление состояния.**
  ТЗ: 11.3, 10.4. WS-endpoint, все типы событий с event_id, дедупликация на клиентской стороне описана в контракте.
  **DoD:** интеграционный тест: подписка mid-pipeline → GET events + WS дают полную историю без дублей по event_id.

- [ ] **T-13. Frontend: экраны Этапа 1.**
  ТЗ: 10.1–10.7, 10.11. Главная (форма FR-04 с двумя флагами и weaved_sources), Написание (hero-статус, 13 шагов, вкладки Лог/Диалог агентов/Результат, восстановление после F5, переключение активных генераций через ?id), Review-панель (редактирование outline, таймер таймаута), Результат, История.
  **DoD:** полный цикл в браузере на MockLLM: форма → генерация → пауза → правка outline → resume → результат; F5 в середине не теряет лог.

- [ ] **T-14. Интеграция и живой прогон. [ЖИВЫЕ LLM-ВЫЗОВЫ РАЗРЕШЕНЫ]**
  ТЗ: 21.1, 21.3. E2E на кэшированном SERP Байкала с живым LLM (1–2 прогона, не больше), сверка с reference_article по качеству, README запуска, Swagger, инструкция администратора.
  **DoD:** `docker compose up` → статья генерируется end-to-end; стоимость и время в пределах 21.2; отчёт заказчику: готовность к приёмке Этапа 1 по 5 темам Приложения D (прогоны по темам запускает заказчик или по его команде).

## Этап 2 — полный объём (старт после приёмки Этапа 1)

- [ ] **T-15. Мультиязычность.** ТЗ: раздел 8. 6 языков: пути промптов, pysbd, стоп-слова, каталог референсов писателей (структура + загрузка; сами тексты согласовать с заказчиком).
- [ ] **T-16. WordPress-публикация.** ТЗ: 15, FR-11. Тестовый сайт заказчика: russiatravelers.online (Application Password запросить у заказчика).
- [ ] **T-17. Экраны Аналитика / Сайты / Настройки.** ТЗ: 10.8–10.10, 11.2.7.
- [ ] **T-18. Самообучение — Стратегия C.** ТЗ: 18.5. pgvector-каталог успешных outline, sentence-transformers, инъекция примеров в outline_agent, ключ кэша с id примеров.
- [ ] **T-19. Smoke-test 5 языков + финальная приёмка.** [ЖИВЫЕ LLM-ВЫЗОВЫ РАЗРЕШЕНЫ] ТЗ: 21 целиком, Приложение D.
