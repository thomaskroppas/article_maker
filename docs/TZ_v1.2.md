# Техническое задание: SEO Pipeline

**Версия документа:** 1.2 (консолидированная: все правки внесены в текст, отдельный документ правок не требуется)
**Дата:** 3 июля 2026
**Заказчик:** руководитель отдела link-building / контент-проектов
**Целевая аудитория:** разработчик (или команда), реализующая приложение с нуля
**Формат разработки:** веб-приложение (браузерная версия с самого начала)

---

## Содержание

1. [Бизнес-контекст и цели проекта](#1-бизнес-контекст-и-цели-проекта)
2. [Общее описание системы](#2-общее-описание-системы)
3. [Функциональные требования](#3-функциональные-требования)
4. [Технический стек и требования к окружению](#4-технический-стек-и-требования-к-окружению)
5. [Архитектура приложения](#5-архитектура-приложения)
6. [Пайплайн генерации статьи](#6-пайплайн-генерации-статьи)
7. [Агенты — детальные спецификации](#7-агенты-—-детальные-спецификации)
8. [Мультиязычность](#8-мультиязычность)
9. [Fact-checking (обязательный агент)](#9-fact-checking-обязательный-агент)
10. [UI — детальные спецификации всех экранов](#10-ui-—-детальные-спецификации-всех-экранов)
11. [API — REST + WebSocket](#11-api-—-rest--websocket)
12. [Схема БД (PostgreSQL)](#12-схема-бд-postgresql)
13. [Схемы данных (Pydantic)](#13-схемы-данных-pydantic)
14. [Внешние интеграции](#14-внешние-интеграции)
15. [Публикация в WordPress](#15-публикация-в-wordpress)
16. [Аналитика и статистика](#16-аналитика-и-статистика)
17. [Кэширование и оптимизации](#17-кэширование-и-оптимизации)
18. [Самообучение приложения](#18-самообучение-приложения)
19. [Docker и деплой](#19-docker-и-деплой)
20. [Промпты агентов (полные тексты как приложение)](#20-промпты-агентов-полные-тексты-как-приложение)
21. [Критерии приёмки](#21-критерии-приёмки)
22. [Технические риски и подводные камни](#22-технические-риски-и-подводные-камни)
23. [Out of scope — что НЕ входит в задачу](#23-out-of-scope-—-что-не-входит-в-задачу)

---

## 1. Бизнес-контекст и цели проекта

### 1.1. Проблема

Ручное написание SEO-статей для контент-проектов — трудоёмкий и медленный процесс. Один автор в среднем пишет 1-2 качественных статьи в день. Для сетки из 15-20 сайтов, каждый из которых требует регулярного обновления, штат авторов масштабируется линейно с количеством сайтов, что экономически невыгодно.

### 1.2. Цель проекта

Создать веб-приложение, которое автоматизирует полный цикл создания SEO-статьи от ввода темы до готового markdown-документа с картинками, метаданными и внутренней разметкой, готового к публикации.

### 1.3. Метрика успеха

- **Скорость:** одна статья от ввода темы до готового результата — не более 10 минут (включая паузу для ручной проверки outline).
- **Качество:** средний QA-score сгенерированной статьи ≥ 80/100.
- **Стоимость LLM:** не более $0.15 за статью (при использовании Claude Sonnet 4.6).
- **Уровень ручной доработки:** статья готова к публикации после ≤ 15 минут ручной правки.

### 1.4. Целевая аудитория пользователей продукта

- SEO-специалисты и контент-менеджеры, работающие с несколькими сайтами.
- Владельцы контент-проектов (агрегаторы, блоги, справочные сайты).
- Индивидуальные авторы, ведущие несколько ниш параллельно.

### 1.5. Ожидаемый режим использования

- Один пользователь (basic auth), возможно расширение до команды в будущем.
- 5-50 статей в день на инсталляцию.
- Локальный запуск через Docker Compose (одна команда).
- Возможность деплоя на VPS заложена архитектурно, но **не входит в приёмку первого релиза** (VPS у заказчика пока нет).

---

## 2. Общее описание системы

### 2.1. Что делает приложение

1. Принимает от пользователя тему статьи и параметры (главный ключ, второстепенные, стиль, стратегия объёма и т.д.).
2. Автоматически анализирует топ-10 поисковой выдачи Google.
3. Формирует ТЗ (Brief) на основе конкурентов.
4. Строит структуру статьи (Outline).
5. Даёт пользователю возможность отредактировать структуру.
6. Пишет каждую секцию через связку Writer → Critic → Editor.
7. Собирает полный markdown, находит и вставляет картинки, генерирует FAQ.
8. Проверяет факты через внешние источники (Wikipedia, Wikidata).
9. Выполняет финальный QA (9 критериев, гибридная оценка).
10. Генерирует метаданные (title, description, tags, JSON-LD).
11. Опционально публикует в WordPress через REST API.

### 2.2. Ключевые компоненты

- **Web frontend** — SPA, интерфейс работы с пайплайном.
- **REST API** — контроллер бизнес-логики.
- **WebSocket** — realtime-события (лог генерации, прогресс, промпты).
- **Celery workers** — асинхронное выполнение пайплайна (одна задача = один пайплайн).
- **Redis** — брокер задач + кэш.
- **PostgreSQL** — метаданные, справочники, статистика.
- **Файловое хранилище** — `data/articles/<slug>_<id>/` с артефактами каждой статьи.
- **LLM-провайдер** — Anthropic Claude API (Sonnet 4.6 + Haiku 4.5).

### 2.3. Многоязычность

Приложение поддерживает генерацию статей на 6 языках с первого релиза:
- Русский (`ru`)
- Английский (`en`)
- Немецкий (`de`)
- Итальянский (`it`)
- Испанский (`es`)
- Французский (`fr`)

Интерфейс приложения — только на русском.

---

## 3. Функциональные требования

### 3.1. FR-01. Управление сайтами

Пользователь может:
- Создавать сайты (домен, название, ниша, is_test флаг).
- Редактировать сайты (кроме домена — он PK).
- Удалять сайты (только если нет привязанных статей).
- Просматривать список всех сайтов с показателями: количество статей, средний QA, средняя стоимость.
- Для каждого сайта — список привязанных авторов.

### 3.2. FR-02. Управление авторами

Пользователь может:
- Создавать авторов (имя, character, tone, age_image, ниша, привязка к сайту, опциональная привязка к style_reference).
- Извлекать стиль автора автоматически: пользователь вставляет несколько абзацев текста конкретного писателя-референса, приложение через `style_extractor_agent` вычленяет стиль/тон/возрастной образ и сохраняет как `style_reference`.
- Использовать style_reference при создании автора (character/tone/age_image подтягиваются автоматически из референса).
- Редактировать авторов.
- Деактивировать авторов (soft-delete через `is_active`).

### 3.3. FR-03. Управление референсами стиля

Пользователь может:
- Добавлять style_references (имя писателя, язык, гео, ниша, текст-референс из 500-2000 слов).
- Сохранённый результат `style_extractor_agent` включает: `extracted_style`, `extracted_tone`, `extracted_age_image`.
- Просматривать все референсы с фильтром по языку/гео/нише.
- Деактивировать референсы.

### 3.4. FR-04. Создание статьи (форма)

Форма создания статьи содержит поля:

**Основные:**
- Сайт (dropdown, обязательно).
- Автор (dropdown, зависит от сайта, опционально).
- Тема статьи (текстовое поле, 5-300 символов, обязательно).
- Главный ключ (текстовое поле, 2-300 символов, обязательно).
- Второстепенные ключи (textarea, по одному на строку, минимум 1 обязательно).
- Стратегия объёма — радио-группа:
  - "Короче топа (0.7 × avg конкурентов)"
  - "Как топ (1.0 × avg)" — **дефолт**
  - "Длиннее топа (1.3 × avg)"
  - "Пользовательская длина" — активирует поле ввода числа.
- Язык (dropdown: ru/en/de/it/es/fr).
- Гео (текстовое поле).
- Интент (radio: informational / how_to).
- Тип статьи (radio: informational / how_to).
- Сложность (radio: easy / medium / hard).
- Стилевой архетип (radio: expert_clear / friendly_practical / calm_analytical / editorial_neutral).

**Дополнительные:**
- Запрещённые слова (textarea).
- Обязательные элементы (чекбоксы: faq / quick_answer / table / list / conclusion / **weaved_sources** — «источники, вплетённые в текст»).
- Пауза для ручного ревью outline (чекбокс, default true).
- Дополнительные заметки (textarea, до 5000 символов).

**Действия:**
- "Проверить данные" — валидация без запуска пайплайна.
- "Запустить пайплайн" — валидация + старт.

### 3.5. FR-05. Пайплайн генерации статьи

При старте пайплайна пользователь автоматически переходит на страницу «Написание». Там отображается:

- **Основной блок:** прогресс шагов (11 из 11) с индикатором текущего.
- **Боковая панель:** список секций (после Outline) с их статусами.
- **Вкладки:**
  - "Лог" — построчный лог событий.
  - "Диалог агентов" — раскрывающиеся блоки промпт/ответ.
  - "Результат" — заполняется после завершения.

Кнопки:
- "Остановить" — прерывает пайплайн (пометка `stopped_by_user`).

### 3.6. FR-06. Пауза для ревью outline (обязательно)

Если `review_outline = true` (default), пайплайн приостанавливается после Шага 5 (Outline). Открывается модальное окно (или overlay-панель) с двумя колонками:

**Левая колонка:**
- Сводка конкурентов: word_count avg / min / max (после trimmed mean), h2_count avg / min / max.
- Список общих H2 конкурентов с их частотой.
- Must-have topics — темы, которые обязательно должны быть в статье.
- Content gaps (точки роста) — темы, которых нет у конкурентов, но которые могут дать преимущество. Каждая с чекбоксом "включить в outline".

**Правая колонка:**
- Suggested archetype с описанием + альтернативы (пользователь может переключить).
- Редактируемый outline: H1 (текстовое поле) + список секций.
- Для каждой секции: title, level (H2/H3), target_word_count (число), кнопки "удалить" и "переместить".
- Кнопка "Добавить секцию".
- Кнопка "Добавить секцию из точек роста" (если пользователь отметил гэпы).
- Сумма target_word_count по всем секциям (общая длина статьи).

Внизу:
- "Отменить генерацию" (пометка stopped_by_user, возврат на форму).
- "Продолжить генерацию" — передаёт отредактированный outline пайплайну.

### 3.7. FR-07. История статей

Страница «История» показывает список всех статей (не тестовых, если фильтр включен). Для каждой статьи:
- Дата создания.
- Тема, главный ключ.
- Сайт, автор.
- Статус, QA-score, стоимость.
- Действие "Открыть" — переход на страницу результата.
- Действие "Открыть папку" (только локальный запуск) или "Скачать архив" (при удалённом).

Фильтры:
- По сайту.
- По статусу (готово / в работе / ошибка / остановлено).
- По датам (от / до).
- По минимальному QA-score.

Сортировка: по дате (desc default), по score, по стоимости.

### 3.8. FR-08. Просмотр результата

После завершения пайплайна пользователь автоматически попадает на страницу «Результат», которая показывает:

**QA-панель:**
- Общий score (0-100) большим кругом.
- Статус (PASS / PASS WITH WARNINGS / FAIL).
- Рекомендации.
- Детализация по 9 критериям с прогресс-барами.
- Предупреждения — **разделённые на группы:**
  - 🔴 **Критические** — блокирующие публикацию.
  - 🟡 **Средние** — рекомендуется править перед публикацией.
  - 🟢 **Незначительные** — можно проигнорировать.

**Метаданные:**
- Slug.
- Meta title (60 символов).
- Meta description (160 символов).
- Теги.
- Категория.

**Просмотр статьи:**
- Переключатель Markdown / Rendered.
- В Rendered — статья с картинками, форматированием.
- Кнопка "Копировать markdown".
- Кнопка "Открыть папку" / "Скачать архив".

**Публикация:**
- Кнопка "Опубликовать в WordPress" (если настроена).

**Информация о времени:**
- Общее время генерации (без пауз).
- Общая стоимость LLM.

### 3.9. FR-09. Аналитика

Страница «Аналитика» с графиками и таблицами:
- Общее количество статей.
- Средний QA-score.
- Средняя стоимость.
- Распределение по QA-статусам.
- Distribution по сайтам.
- Тренд по неделям.
- Топ авторов по QA.
- Экспорт в CSV.

### 3.10. FR-10. Управление настройками

Страница «Настройки»:
- API ключи (LLM, картинки, XMLStock). Хранятся в БД с шифрованием (см. таблицу `app_settings`), редактируются через UI без рестарта контейнеров.
- Настройки WordPress — per-site на экране «Сайты» (URL, user, application password).
- Инвалидация кэша (SERP / agent / image_keys / translation).

### 3.11. FR-11. Публикация в WordPress

Возможность одним кликом опубликовать готовую статью:
- Загрузить картинки в медиа-библиотеку WP.
- Заменить локальные пути в markdown на URLs WP.
- Создать пост со статусом "черновик".
- Установить title, meta_description, tags, категорию.
- Опционально — установить featured image.

### 3.12. FR-12. Fact-checking (обязательно)

**Шаг 11 пайплайна** (после шага 10 — sources_weaver, перед шагом 12 — Final QA):
- `fact_checker_agent` извлекает атомарные утверждения из статьи.
- Каждое утверждение проверяется через Wikipedia REST API + Wikidata SPARQL.
- Отчёт передаётся в final_qa_agent как контекст для оценки factuality.
- Mismatch-утверждения помечаются в QA warnings как критические/средние.

Детали — см. раздел [9. Fact-checking](#9-fact-checking-обязательный-агент).

### 3.13. FR-13. Sources weaver (обязательно)

Между Writer/FAQ и final_qa — новый агент `sources_weaver_agent`:
- Читает готовую статью.
- Вплетает 3-5 ссылок на авторитетные источники **прямо в текст** (например, «согласно [ЮНЕСКО](url)», «по данным [Britannica](url)»).
- НЕ создаёт отдельный блок в конце.
- Не более 1 ссылки на секцию.
- Приоритет — научные источники (Britannica, ЮНЕСКО, госсайты).

После внедрения `sources_block` убирается из required_elements — заменяется на `weaved_sources` (проверка кодом что в статье есть N ссылок с http/https).

### 3.14. FR-14. Умное усреднение конкурентов

При анализе SERP `avg` длины и количества H2 считается через **trimmed mean** (усечённое среднее):
- Убирается минимум и максимум.
- Среднее остальных.

Это исключает выбросы (Википедия на 12k слов) и даёт реальный ориентир.

### 3.15. FR-15. Length control от суммы outline

QA-метрика `length_control` считается от **суммы target_word_count всех секций outline**, не от `brief.word_count_target`. Причина: после ручного ревью outline пользователь мог изменить план длины, и это финальное намерение.

### 3.16. FR-16. Разделение QA warnings

Промпт `final_qa_agent` меняет формат ответа:
```json
{
  "warnings": {
    "critical": ["Отсутствует блок FAQ", ...],
    "medium":   ["Дублирование информации в секциях 3 и 5", ...],
    "minor":    ["Средняя длина конкурентов 3200 слов, у нас 2800", ...]
  }
}
```

В UI три раздела с иконками 🔴 🟡 🟢.

### 3.17. FR-17. Время генерации

Отслеживается:
- `started_at` — момент старта пайплайна.
- `finished_at` — момент завершения.
- Периоды пауз (review_ready → resume_with_outline) исключаются.

**Итоговая метрика:** `finished_at - started_at - sum(pause_durations)` в секундах, показывается в результате.

### 3.18. FR-18. Дедупликация точек роста

При формировании review-панели: content_gaps фильтруются от тех, что уже присутствуют в outline.sections (по совпадению title). Дубли не показываются.

---

*Продолжение в части 2 (стек, архитектура, API, спецификации агентов и остальное)*

---

## 4. Технический стек и требования к окружению

### 4.1. Backend

| Компонент | Технология | Обязательная версия |
|---|---|---|
| Runtime | Python | 3.11+ |
| Web framework | FastAPI | 0.110+ |
| ASGI сервер | Uvicorn | 0.27+ |
| Task queue | Celery | 5.3+ |
| Message broker | Redis | 7.0+ |
| WebSocket | FastAPI WebSocket (built-in) | — |
| DB | PostgreSQL | 15+ |
| DB driver | psycopg2-binary (или asyncpg) | latest |
| ORM/Schemas | Pydantic + SQLAlchemy 2.0 | latest |
| LLM SDK | anthropic | 0.34+ |
| Auth | fastapi-users или собственная basic auth | — |
| Image processing | Pillow | 10+ |
| HTML parsing | BeautifulSoup4 + lxml + readability-lxml | latest |
| Sentence splitting | pysbd | latest |
| Embeddings (Стратегия C) | sentence-transformers | latest |

### 4.2. Frontend

| Компонент | Технология | Обязательная версия |
|---|---|---|
| Framework | React 18 или Vue 3 | latest |
| Build | Vite | 5+ |
| Routing | React Router / Vue Router | latest |
| State | Zustand или Pinia | latest |
| Styling | Tailwind CSS | 3+ |
| HTTP | Axios или Fetch | — |
| WebSocket | Native WebSocket API или socket.io-client | — |
| Markdown render | marked или react-markdown | latest |

**Обоснование выбора React vs Vue:** оставлено на усмотрение разработчика. Рекомендуется React из-за большей экосистемы, но Vue также допустим.

### 4.3. Инфраструктура

| Компонент | Технология |
|---|---|
| Контейнеризация | Docker + Docker Compose |
| Reverse proxy | Nginx (в docker-compose) |
| SSL | Let's Encrypt (в продакшене) |
| Логи | JSON logs + logrotate |

### 4.4. Внешние API (обязательные)

- **Anthropic Claude API** — SDK `anthropic`.
- **XMLStock SERP** — self-hosted парсер на HTTP.
- **Pixabay** — REST API.
- **Unsplash** — REST API.
- **Wikimedia Commons** — REST API (без ключа).
- **Wikipedia REST API** — для fact-checking (без ключа).
- **Wikidata SPARQL** — для fact-checking (без ключа).
- **WordPress REST API** — для публикации.

### 4.5. Требования к окружению

**Локальный запуск (dev):**
- Docker 24+.
- Docker Compose v2.
- 4 GB RAM минимум.
- 20 GB свободного места (для картинок и кэша).

**Продакшен (VPS) — справочно, вне приёмки первого релиза:**
- 2 CPU, 4 GB RAM, 50 GB SSD.
- Публичный IP или домен.
- Открытые порты: 80, 443 (SSL).

---

## 5. Архитектура приложения

### 5.1. Высокоуровневая схема

```
[Пользователь]
     ↓ HTTPS
[Nginx reverse proxy] :443
     ├─→ /api/*   → [FastAPI backend] :8000
     ├─→ /ws/*    → [FastAPI WebSocket] :8000
     └─→ /*        → [React frontend] :3000
                     
[FastAPI backend] :8000
     ├─→ [Celery queue] via Redis
     ├─→ [PostgreSQL] :5432
     └─→ [File storage] /data
                     
[Celery worker] (executes pipelines)
     ├─→ [Anthropic API]
     ├─→ [XMLStock SERP]
     ├─→ [Pixabay/Unsplash/Wikimedia]
     ├─→ [Wikipedia/Wikidata]
     ├─→ [PostgreSQL]
     └─→ [File storage] /data
```

### 5.2. Компоненты и их ответственность

**FastAPI backend:**
- REST endpoints для CRUD (sites, authors, articles, references).
- WebSocket endpoints для realtime-событий.
- Валидация Pydantic-схемами.
- Публикация задач в Celery.
- Basic auth middleware.

**Celery worker:**
- Единственная задача типа `run_pipeline(article_input_json)`.
- Внутри задачи — весь оркестратор пайплайна (11 шагов).
- Публикует события через Redis pub/sub, backend их пересылает по WebSocket.

**PostgreSQL:**
- Метаданные: sites, authors, references, articles, pipeline_steps, sections, archetype_picks, niches, archetypes.
- Аналитика: агрегированные view для быстрого доступа.

**File storage /data:**
- `data/articles/<slug>_<id>/` — артефакты каждой статьи.
- `data/serp_cache/` — кэш SERP.
- `data/agent_cache/` — кэш агентов.
- `data/image_keys_cache.json` — кэш ключей.
- `data/translation_cache.json` — кэш переводов.
- `data/wiki_cache/` — кэш Wikipedia/Wikidata запросов (для fact-checker).

**React frontend:**
- Роутинг: `/`, `/write`, `/result/:article_id`, `/history`, `/sites`, `/analytics`, `/settings`.
- Zustand store для глобального состояния (текущая генерация, счётчики стоимости).
- WebSocket-клиент для realtime-обновлений.

### 5.3. Поток данных при запуске пайплайна

1. Пользователь заполняет форму → `POST /api/pipeline/run` с `ArticleInput` JSON.
2. Backend валидирует, создаёт запись в `articles` (status='created'), кладёт задачу в Celery: `run_pipeline.delay(article_id)`.
3. Backend возвращает `{article_id, ws_url}`.
4. Frontend редиректит на `/write` и подключается к `ws://.../ws/pipeline/{article_id}`.
5. Celery worker берёт задачу, начинает пайплайн. По ходу публикует события в Redis pub/sub канал `pipeline:{article_id}`.
6. Backend через WebSocket пересылает события фронту.
7. Frontend обновляет UI в реальном времени.
8. При необходимости паузы для ревью — worker публикует событие `{type: "review_ready", data: {...}}` и ждёт `{type: "review_confirmed", data: {...}}` через Redis subscription.
9. Frontend показывает review-панель, отправляет `POST /api/pipeline/{article_id}/resume` с отредактированным outline.
10. Backend публикует `review_confirmed` в Redis, worker продолжает.
11. По завершении — событие `{type: "finished", data: {qa_result, final_package}}`, worker обновляет `articles.status`.

### 5.4. Пауза и остановка (детально)

**Остановка:** пользователь жмёт кнопку → `POST /api/pipeline/{article_id}/stop`. Backend публикует в Redis `pipeline:control:{article_id}` событие `{action: "stop"}`. Worker в конце каждого шага проверяет наличие сообщения — если есть, поднимает исключение `PipelineStopped`, помечает статус.

**Пауза для ревью:** реализуется через `redis.subscribe('review_confirmed:{article_id}')`. Worker блокируется на `pubsub.listen()` до получения сообщения.

---

## 6. Пайплайн генерации статьи

Оркестратор реализует **11 обязательных шагов + 1 опциональная пауза + 1 обязательный fact-check + 1 обязательный sources weaver**.

### 6.1. Обзор шагов

| # | Шаг | Тип | Агент | Модель |
|---|---|---|---|---|
| 1 | SERP-анализ | Внешний вызов | — | — |
| 2 | Анализ конкурентов | LLM | competitor_analysis_agent | Sonnet |
| 3 | LSI-ключи | LLM | lsi_agent | Haiku |
| 4 | Формирование ТЗ (Brief) | LLM | brief_agent | Sonnet |
| 5 | Outline (структура) | LLM | outline_agent | Sonnet |
|   | Пауза для ревью | Ручное действие | — | — |
| 6 | Секции (по каждой) | LLM (циклом) | writer + critic + editor | Sonnet |
| 7 | Сборка markdown | Код | markdown_builder | — |
| 8 | Картинки | LLM + внешние | image_finder_agent | Haiku |
| 9 | FAQ (если нужен) | LLM | faq_writer_agent | Sonnet |
| 10 | Вплетение источников | LLM + внешние | sources_weaver_agent | Sonnet |
| 11 | Fact-checking | LLM + внешние | fact_checker_agent | Sonnet |
| 12 | Финальный QA | LLM + код | final_qa_agent | Sonnet |
| 13 | Метаданные | LLM | metadata_agent | Sonnet |

**Пайплайн состоит из 13 шагов.** Шаги 10 (sources_weaver) и 11 (fact_checker) — новые, отсутствуют в референсной desktop-версии; их промпты разрабатываются в рамках этого проекта (см. п. 20.5). Нумерация шагов ниже — каноническая, используется везде: UI, WebSocket-события, pipeline_steps.step_number, логи. Пауза для ревью структуры номера не имеет (происходит между шагами 5 и 6).

### 6.2. Требования к каждому шагу

**Общие требования ко всем шагам:**
- Проверка на stop-сигнал перед стартом.
- Логирование старта и окончания в pipeline_steps + WebSocket-событие.
- Сохранение результата на диск (`data/articles/<dir>/<step_name>.json`).
- Сохранение промпта и ответа LLM (для LLM-шагов).
- Обработка исключений: логируется в error_message, статус statья = failed.
- Учёт стоимости LLM-вызова.

**Кэшируемые шаги:**
- competitor_analysis_agent
- lsi_agent
- brief_agent
- outline_agent

Ключ кэша: `{agent}:{article_title.lower()}:{main_keyword.lower()}:{sorted_secondary_keywords}`.

### 6.2.1. Константы пайплайна (config)

```python
QA_SCORE_PASS = 85          # score >= 85 → status 'pass'
QA_SCORE_WARN = 70          # score >= 70 → 'pass_with_warnings', иначе 'fail'
CRITIC_PASS_SCORE = 60      # порог принятия секции Critic'ом
SECTION_MAX_ITERATIONS = 3  # максимум циклов Writer/Editor → Critic на секцию
REVIEW_TIMEOUT_HOURS = 4    # авто-отмена пайплайна, зависшего на ревью (см. 6.8.1)
FACT_CHECK_MAX_STATEMENTS = 20
```

Все константы выносятся в конфиг и могут быть переопределены через переменные окружения.

### 6.3. Шаг 1: SERP-анализ

**Задача:** получить топ-10 URLs по main_keyword в Google + распарсенное содержимое.

**Логика:**
1. Проверить SERP-кэш (`data/serp_cache/<hash>.json`, где hash = sha256(`main_keyword|geo|language`)).
2. Если есть и `force_refresh_serp=False` — использовать.
3. Иначе:
   - HTTP GET на XMLStock: `{URL}?q={main_keyword}&geo={geo}&hl={language}`.
   - Ответ содержит список объектов `{url, title, description}`.
   - Для каждого URL: HTTP GET, парсинг через readability-lxml для извлечения main content.
   - Сохранить в кэш.
4. Отдать `SerpBundle`.

**Альтернативные источники SERP (взаимоисключающие, приоритет сверху вниз):**

1. `serp_json_path` задан → загрузить готовый `SerpBundle` из указанного JSON-файла (валидация Pydantic-схемой). XMLStock не вызывается, кэш не используется. Назначение: повторные прогоны и тесты на фиксированной выдаче.
2. `manual_sources` задан (список URL) → XMLStock не вызывается. Каждый URL скачивается и парсится через readability-lxml так же, как в основном потоке; из результатов собирается `SerpBundle` (`query = main_keyword`). Назначение: пользователь сам знает эталонных конкурентов.
3. Иначе — стандартный поток (кэш → XMLStock).

В UI эти параметры не выводятся в форму первого релиза — доступны только через API (используются для тестов и приёмки).

**Схема SerpBundle:**
```python
class SerpItem(BaseModel):
    url: str
    title: str
    description: str
    content: str
    h1: Optional[str]
    h2_list: List[str]
    h3_list: List[str]
    word_count: int

class SerpBundle(BaseModel):
    query: str
    geo: str
    language: str
    items: List[SerpItem]
    fetched_at: datetime
```

**Ошибки:** если XMLStock недоступен и нет кэша — пайплайн падает с ошибкой "SERP недоступен, попробуйте позже".

### 6.4. Шаг 2: Анализ конкурентов

**Задача:** проанализировать топ-10 конкурентов, дать структурированный отчёт.

**Логика:**
1. Формируется выжимка из SerpBundle: для каждого топ-URL — только title, H1, H2, H3 и первые 300 слов текста.
2. Передаётся в `competitor_analysis_agent`.
3. LLM возвращает JSON согласно схеме CompetitorAnalysisReport.

**Требование к trimmed mean:**
- В `word_count_range.avg` — trimmed mean (без min и max) от `[item.word_count for item in serp_bundle.items]`.
- В `h2_count_range.avg` — тот же trimmed mean от количества H2 у каждого конкурента.
- `min` и `max` тоже сохраняются — но как справочная информация, не для среднего.

**Fallback при малой выборке:**
- N >= 5 конкурентов → trimmed mean (без min и max).
- N = 3-4 → медиана.
- N = 1-2 → обычное среднее + warning в лог «Мало конкурентов в SERP, ориентир длины ненадёжен» (также передаётся в review-панель).
- N = 0 → пайплайн падает на шаге 1 (см. ошибки шага 1).

**Кэшируется.**

### 6.5. Шаг 3: LSI-ключи

**Задача:** извлечь 15-25 английских LSI-слов для последующего поиска картинок.

**Логика:**
1. LLM получает выжимку из competitor_report (must_have_topics + content_gaps + common_h2).
2. Возвращает JSON-массив строк на английском.

**Кэшируется.**

### 6.6. Шаг 4: Формирование ТЗ (Brief)

**Задача:** сформировать структурированное ТЗ.

**Логика:**
1. Внутри агента считается `target_word_count` через `_compute_target_word_count`:
   ```python
   MULTIPLIERS = {"shorter_top": 0.7, "match_top": 1.0, "longer_top": 1.3}
   if length_strategy == "custom":
       target = article_input.target_word_count
   else:
       target = round(competitor_report.word_count_range.avg * MULTIPLIERS[length_strategy])
   ```
2. LLM генерирует Brief со всеми полями. Пересчитанный `target_word_count` передаётся как готовая величина.
3. `lsi_keywords` не входят в промпт brief_agent'а — они добавляются в `Brief.lsi_keywords` уже в оркестраторе (после вызова).

**Кэшируется.**

### 6.7. Шаг 5: Outline (структура)

**Задача:** составить структуру статьи (H1 + список секций).

**Логика:**
1. LLM получает Brief + краткую сводку конкурентов.
2. Возвращает Outline.
3. Оркестратор проверяет: сумма `target_word_count` секций близка к `brief.word_count_target`. Если разница >20% — предупреждение в лог.

**Кэшируется.**

### 6.8. Пауза для ручного ревью

Если `article_input.review_outline=True`:
1. Оркестратор публикует WebSocket-событие:
   ```json
   {
     "type": "review_ready",
     "data": {
       "competitor_summary": {...},
       "content_gaps_filtered": [...],   // с удалением совпадений с sections
       "archetype_suggestion": {...},
       "outline": {...}
     }
   }
   ```
2. Ждёт `review_confirmed` через Redis pubsub.
3. При получении — использует отредактированный outline и продолжает.

#### 6.8.1. Таймаут ревью

Пауза для ревью блокирует worker-слот Celery. Чтобы зависшие ревью не парализовали очередь (при `--concurrency=2` два забытых ревью блокируют всё):

- `pubsub.listen()` вызывается с таймаутом; общее время ожидания ограничено `REVIEW_TIMEOUT_HOURS` (default 4, конфигурируемо).
- По истечении — пайплайн завершается со статусом `review_timeout`, WebSocket-событие `aborted` с `reason: "review_timeout"`.
- Кэши агентов (brief, outline) при этом сохраняются — повторный запуск той же темы пройдёт шаги 2-5 мгновенно и снова откроет ревью.
- В UI на review-панели показывается таймер оставшегося времени.

**Content gaps filtering (FR-18):**
```python
outline_titles = {s.title.lower() for s in outline.sections}
filtered_gaps = [g for g in competitor_report.content_gaps
                 if g.title.lower() not in outline_titles]
```

### 6.9. Шаг 6: Секции

**Задача:** написать каждую секцию outline через связку Writer → Critic → Editor.

**Логика (для каждой SectionSpec):**
1. Собирается контекст: `article_input`, `brief`, `section_spec`, `author`, резюме предыдущих секций.
2. Вызов Writer → текст секции + `<!-- SUMMARY: ... -->` маркер.
3. Если `article_input.enable_section_critic=True`:
   - Вызов Critic → CriticFeedback (score + issues).
   - Если score >= CRITIC_PASS_SCORE (60) → секция готова.
   - Иначе → Editor редактирует с учётом issues → снова Critic.
   - Максимум SECTION_MAX_ITERATIONS (3) итераций.

   Если `enable_section_critic=False` — секция принимается после первого прохода Writer (быстрый/дешёвый режим).
4. Сохраняется как `SectionFinal(section_id, title, content)`.

**Контекст предыдущих секций:**
После каждой секции извлекается `<!-- SUMMARY: ... -->` — краткое резюме фактов. Передаётся Writer'у следующей секции чтобы избежать противоречий (25-30 vs 25-35 млн лет).

### 6.10. Шаг 7: Сборка markdown

**Задача:** собрать финальный markdown.

**Логика:**
1. Начать с `# {outline.h1}`.
2. Для каждой SectionFinal:
   - Если title содержит "quick_answer" или похожие "no-heading" маркеры — вставить только content без заголовка.
   - Иначе — вставить `## {title}` или `### {title}` + content.
3. Удалить `<!-- SUMMARY: ... -->` маркеры.
4. Проверить наличие FAQ секции в outline.sections (по title/section_id "faq"). Если есть — `has_faq_in_sections=True`.
5. Вернуть FullDraft.

### 6.11. Шаг 8: Картинки

**Задача:** найти и вставить релевантные картинки.

**Логика:**
1. Найти точки вставки в markdown:
   - Плейсхолдеры `<!-- IMAGE: описание -->` от Writer'а.
   - Автоматически после H2/H3 (интервал ~250 слов, мин. секция 60 слов, исключая "FAQ", "Заключение", "Источники").
2. Через image_keys_agent (Haiku) получить 10 английских ключей для поиска (кэшируется по main_keyword).
3. Для каждой точки:
   - По очереди: Pixabay → Unsplash → Wikimedia.
   - Дедупликация по URL через used_urls set.
   - Ротация ключей при HTTP 429.
4. Скачать выбранную картинку через `image_processor`:
   - Resize до 1920 по длинной стороне (если больше).
   - Crop 16:9 из центра.
   - Конвертация в WebP quality=70.
   - Сохранение в `<article_dir>/images/N.webp`.
5. Вставить в markdown: `![alt](images/N.webp)\n*Источник: [название](provider_url)*`.

### 6.12. Шаг 9: FAQ

**Задача:** сгенерировать блок FAQ по вопросам из outline.faq_section.

**Логика:**
1. Если `has_faq_in_sections=True` или `outline.faq_section.enabled=False` — пропустить.
2. Иначе — вызвать `faq_writer_agent.run_with_questions(...)`:
   - Промпту передаётся выжимка статьи, brief.must_cover (эталонные факты), автор, список вопросов.
   - Возвращает markdown-блок FAQ.
3. Вставить перед секцией "Заключение" через regex `^##\s+(заключен|итог|подводя|conclusion|conclusione|schluss|resumen)`.
4. Если такой секции нет — вставить в конец.

### 6.13. Шаг 10: Вплетение источников (sources_weaver_agent)

**Задача:** вплести 3-5 ссылок на авторитетные источники в текст статьи.

**Логика:**
1. Агент получает готовый markdown + список авторитетных источников (можно из внешнего списка + запроса Wikipedia).
2. Возвращает статью с добавленными inline-ссылками вида `согласно [ЮНЕСКО](url)`.
3. Правила:
   - Не более 1 ссылки на секцию.
   - Только там, где реально ссылается на факт.
   - Приоритет — научные источники и госсайты.
4. Оригинальный текст не меняется, только добавляются ссылки.

### 6.14. Шаг 11: Fact-checking (fact_checker_agent)

**Задача:** проверить факты статьи через внешние базы данных.

Детали — см. раздел [9. Fact-checking](#9-fact-checking-обязательный-агент).

### 6.15. Шаг 12: Финальный QA

**Задача:** оценить статью по 9 критериям.

**Логика:**
1. **Код (`qa_metrics.calc_code_metrics`)** — считает 6 критериев:
   - `length_control` — отклонение от `sum(outline.sections.target_word_count)` (не от brief!).
   - `completeness` — доля найденных `required_elements`. Проверка `weaved_sources` выполняется кодом: в тексте статьи (вне блока FAQ) присутствует >= 3 markdown-ссылок вида `[текст](http...)` на внешние домены.
   - `keyword_usage` — main density * 0.7 + secondary coverage * 0.3.
   - `structure` — H1, H2, H3, введение.
   - `readability` — доля предложений >20 слов, <8 слов.
   - `lsi_coverage` — доля LSI-слов найдённых в тексте.
2. **LLM (`final_qa_agent`)** — оценивает 3 субъективных:
   - `brief_alignment`.
   - `intent_coverage`.
   - `factuality` (с учётом отчёта fact_checker).
3. Отчёт fact_checker передаётся LLM как контекст: mismatch-утверждения снижают factuality.
4. Warnings разделяются на critical / medium / minor.

**Итог:** QAResult со score = взвешенная сумма 9 критериев.

**Правило независимо от score:** если fact_check_report содержит >20% mismatches — итоговый статус не может быть выше `pass_with_warnings`, даже при score >= 85. Все mismatch-утверждения попадают в `warnings.critical`.

### 6.16. Шаг 13: Метаданные

**Задача:** сгенерировать FinalPackage для публикации.

**Логика:**
1. LLM получает full_draft + brief + outline.
2. Возвращает: slug (URL-friendly), meta_title (60 chars), meta_description (160 chars), tags (5-10), category, internal_links_suggestions, schema_data (JSON-LD FAQPage).
3. Сохраняется как final_package.json.

---

*Продолжение в части 3 (агенты подробно, мультиязычность, fact-checking, UI, API)*

---

## 7. Агенты — детальные спецификации

### 7.1. Общий контракт агента

Все агенты наследуются от базового класса `BaseAgent` с интерфейсом:

```python
class BaseAgent:
    agent_name: str                      # "brief_agent" и т.д.
    llm_client: LLMClient                # клиент к Anthropic API
    stop_flag: threading.Event           # для прерывания retry
    last_prompt: str                     # для сохранения
    last_response: str                   # для сохранения
    last_tokens_in: int                  # для cost tracking
    last_tokens_out: int                 # для cost tracking

    def _call(self, variables: dict) -> LLMResponse
    def _parse_json(self, text: str) -> Union[dict, list]
    def set_stop_flag(self, flag: threading.Event)
```

`_call` подставляет переменные в промпт (из файла `prompts/<agent_name>/v1.txt`), вызывает LLM с параметрами из `AGENT_PARAMS`, ретраит при 429/500 через `retry_service`.

### 7.2. Список всех агентов

| Агент | Модель | max_tokens | temperature | Задача (кратко) |
|---|---|---|---|---|
| competitor_analysis_agent | Sonnet | 8192 | 0.3 | Анализ топ-10 конкурентов |
| lsi_agent | Haiku | 800 | 0.2 | LSI-ключи для картинок |
| brief_agent | Sonnet | 8192 | 0.4 | Структурированное ТЗ |
| outline_agent | Sonnet | 8192 | 0.3 | Структура статьи |
| writer_agent | Sonnet | 8192 | 0.7 | Написание секции |
| critic_agent | Sonnet | 4096 | 0.2 | Оценка секции |
| editor_agent | Sonnet | 8192 | 0.6 | Правка секции |
| faq_writer_agent | Sonnet | 2000 | 0.6 | FAQ-блок |
| **sources_weaver_agent** | Sonnet | 4096 | 0.4 | Вплетение источников (новый) |
| **fact_checker_agent** | Sonnet | 4096 | 0.2 | Проверка фактов (новый) |
| image_finder_agent | Sonnet (для перевода) + Haiku (для ключей) | — | — | Поиск и вставка картинок |
| image_keys_agent | Haiku | 500 | 0.3 | Ключи для поиска картинок |
| final_qa_agent | Sonnet | 2048 | 0.2 | Финальная оценка |
| metadata_agent | Sonnet | 4096 | 0.4 | Метаданные для публикации |
| archetype_picker_agent | Haiku | 512 | 0.1 | Подбор архетипа |
| style_extractor_agent | Haiku | 1500 | 0.3 | Извлечение стиля из референса |

### 7.3. Спецификация каждого агента

Полные тексты промптов — в разделе [20](#20-промпты-агентов-полные-тексты-как-приложение).

#### 7.3.1. competitor_analysis_agent

**Вход:** article_input, serp_bundle (выжимка).
**Выход:** CompetitorAnalysisReport.

**Требования:**
- avg длины через trimmed mean (без min/max).
- Выделить min. 3, max. 8 content_gaps (точек роста).
- Выделить min. 3 must_have_topics — обязательные темы у большинства конкурентов.
- В common_h2_titles — только те H2, что встречаются у ≥3 конкурентов.

#### 7.3.2. lsi_agent

**Вход:** article_input, competitor_report.
**Выход:** List[str] на английском.

**Требования:**
- 15-25 ключей.
- Каждый ключ 1-3 слова.
- Не дублировать main_keyword и secondary_keywords.

#### 7.3.3. brief_agent

**Вход:** article_input, competitor_report.
**Выход:** Brief.

**Требования:**
- Внутри агента: `_compute_target_word_count()` — формула по стратегии.
- В Brief: goal, target_audience, must_cover (10-15 пунктов), must_not_cover, structure_guidelines, keywords, required_elements, forbidden_words, data_handling_rules.
- `data_handling_rules` формируется на основе `competitor_report.data_sensitivity`: если `has_volatile_data=True` → `avoid_exact_dates=True`, `use_approximate_language=True` (формулировки вида «по состоянию на 2026 год», «около», «порядка»). Логика — в коде агента, LLM получает готовые правила в промпте.

#### 7.3.4. outline_agent

**Вход:** article_input, brief, competitor_report.
**Выход:** Outline.

**Требования:**
- Каждая секция имеет `section_id` формата `s0`, `s1`, `s1_1`, `s2`, ...
- `s0` часто = "quick_answer" (H2, no-heading в финальном md).
- Опционально — `faq_section.enabled=True` с 5-7 вопросами.
- Проверка: если Brief.required_elements содержит "faq" — outline должен либо включить секцию "FAQ" в sections либо `faq_section.enabled=True`.

#### 7.3.5. writer_agent

**Вход:** article_input, brief, section_spec, author (опционально), previous_sections_summaries (List[str]), lsi_keywords.
**Выход:** markdown секции + `<!-- SUMMARY: ключевые факты -->`.

**Требования:**
- Промпт содержит блок "АВТОР СТАТЬИ" с character/tone/age_image.
- Соблюдать target_word_count ±15%.
- Не использовать forbidden_words.
- Использовать LSI-ключи естественно (не более 2 на секцию).
- Может вставлять `<!-- IMAGE: описание -->` где нужна картинка.
- Обязательно завершать `<!-- SUMMARY: ключевые факты и цифры -->` — оркестратор извлечёт и передаст следующей секции.

#### 7.3.6. critic_agent

**Вход:** section_text, section_spec, brief.
**Выход:** CriticFeedback.

**Схема CriticFeedback:**
```python
class CriticFeedback(BaseModel):
    overall_score: int              # 0-100
    per_criterion: dict             # {content_quality, keyword_usage, structure, factuality, readability, alignment_with_brief}
    issues: List[str]               # конкретные проблемы
    suggestions: List[str]          # конкретные рекомендации
```

**Требования:**
- Промпт содержит калибровку шкалы: **60+ — публикабельно, ниже 40 — переписать полностью**. Не сваливаться в 0 из-за одной проблемы.
- Не сваливаться в 0 из-за одной проблемы.

#### 7.3.7. editor_agent

**Вход:** section_text, critic_feedback, section_spec.
**Выход:** переписанный текст.

**Требования:**
- Учесть все issues из feedback.
- Не менять факты произвольно.
- Соблюдать target_word_count.

#### 7.3.8. faq_writer_agent

**Вход:** article_input, brief, article_markdown, questions (List[str]), author.
**Выход:** markdown-блок FAQ.

**Требования:**
- Ответы 40-60 слов.
- Прямой ответ первым предложением (для Google featured snippet).
- Стиль автора.
- Не противоречить статье (сверка с brief.must_cover и извлечёнными фактами).

#### 7.3.9. sources_weaver_agent (новый)

**Вход:** article_markdown, main_keyword, language.
**Выход:** article_markdown с вплетёнными ссылками.

**Требования:**
- **3-5 ссылок на всю статью** (не на секцию), не более 1 ссылки на секцию.
- Только там, где реально ссылается на факт.
- Не более 1 ссылки на секцию.
- Приоритет — научные источники (Britannica, ЮНЕСКО, госсайты, Wikipedia).
- Автоматически проверить что все URL живые (HEAD-запрос).

**Логика:**
1. Определить факты из статьи (можно через LLM экстракшн, или регексами: числа + единицы измерения, имена собственные + место).
2. Для каждого — попробовать найти в Wikipedia REST API (`https://<lang>.wikipedia.org/api/rest_v1/page/summary/{title}`).
3. Если нашлось — получить URL Wikipedia.
4. Для научных фактов — искать через Britannica search.
5. Выбрать 3-5 наилучших фактов для вплетения.
6. LLM вплетает ссылки в текст, сохраняя стиль.

#### 7.3.10. fact_checker_agent (новый)

**Вход:** article_markdown, language.
**Выход:** FactCheckReport.

**Схема FactCheckReport:**
```python
class FactStatement(BaseModel):
    text: str                    # оригинальное предложение
    type: str                    # numeric | date | location | name
    subject: str                 # "Байкал"
    property: Optional[str]      # "глубина"
    value_in_article: str        # "1642 м"

class FactCheckResult(BaseModel):
    statement: FactStatement
    status: str                  # verified | mismatch | uncertain
    external_value: Optional[str]
    source_url: Optional[str]
    confidence: float            # 0.0 - 1.0

class FactCheckReport(BaseModel):
    total_statements: int
    verified: int
    mismatches: int
    uncertain: int
    results: List[FactCheckResult]
```

Детали — см. раздел [9](#9-fact-checking-обязательный-агент).

#### 7.3.11. image_finder_agent

**Вход:** article_markdown, main_topic, main_keyword, article_dir, language.
**Выход:** обновлённый markdown с картинками + файлы в `<article_dir>/images/`.

**Требования:**
- Точки вставки: плейсхолдеры Writer'а + автоматически после H2/H3 (~250 слов).
- 10 английских ключей через image_keys_agent.
- Кэш ключей по main_keyword.
- Провайдеры: Pixabay → Unsplash → Wikimedia.
- Дедупликация по URL.
- Обработка: resize до 1920, crop 16:9, WebP 70.

#### 7.3.12. image_keys_agent

**Вход:** main_keyword, article_title, language.
**Выход:** List[str] — 10 английских ключей.

**Требования:**
- Ключи для поиска в стоковых сервисах.
- Разнообразие: разные аспекты темы.
- Кэш по main_keyword.

#### 7.3.13. final_qa_agent

**Вход:** article_input, brief, competitor_report, full_draft, fact_check_report, outline.
**Выход:** QAResult с разделёнными warnings.

**Требования:**
- Гибридная оценка: 6 критериев кодом, 3 LLM.
- Length_control считать от `sum(outline.sections.target_word_count)`, не от brief.
- Warnings разделены на critical/medium/minor.
- LLM получает fact_check_report в контексте для оценки factuality.

**Веса критериев:**
```python
WEIGHTS = {
    "brief_alignment":  0.20,
    "completeness":     0.20,
    "intent_coverage":  0.15,
    "keyword_usage":    0.10,
    "lsi_coverage":     0.05,
    "readability":      0.10,
    "structure":        0.10,
    "factuality":       0.05,
    "length_control":   0.05,
}
```

#### 7.3.14. metadata_agent

**Вход:** article_input, brief, outline, full_draft.
**Выход:** FinalPackage.

**Требования:**
- slug: URL-friendly, транслит + дефисы, ≤50 символов.
- meta_title: ≤60 символов.
- meta_description: ≤160 символов.
- tags: 5-10 штук.
- schema_data: JSON-LD FAQPage (если есть FAQ).

#### 7.3.15. archetype_picker_agent

**Вход:** article_title, main_keyword, niche_id.
**Выход:** {suggested_archetype_id, alternatives}.

**Требования:**
- Использовать список архетипов из БД по nichе.
- Suggested — один наиболее подходящий.
- Alternatives — все остальные из этой ниши.

#### 7.3.16. style_extractor_agent

**Вход:** name (автора), reference_text (500-2000 слов).
**Выход:** {extracted_style, extracted_tone, extracted_age_image}.

**Требования:**
- extracted_style: краткая характеристика литературного стиля (2-3 предложения).
- extracted_tone: список тональностей (ироничный, серьёзный, эмоциональный и т.д.).
- extracted_age_image: возрастной образ автора (по характеру речи).

---

## 8. Мультиязычность

### 8.1. Требования

Приложение поддерживает генерацию статей на 6 языках с первого релиза:
- Русский (`ru`)
- Английский (`en`)
- Немецкий (`de`)
- Итальянский (`it`)
- Испанский (`es`)
- Французский (`fr`)

### 8.2. Реализация

#### 8.2.1. Промпты агентов

Все промпты параметризованы через `$language`. Пример writer_agent v1.txt:

```
# ROLE
You are a senior SEO editor writing ONE section of an article in $language.
Language: $language

...

# LANGUAGE
Language of the article: $language. Write ONLY in $language.
```

Промпты хранятся как одинаковые файлы для всех языков. Инструкция в промпте: "write in $language". LLM Claude уверенно справляется на всех 6 языках.

#### 8.2.2. Стоп-слова

Загружаются из библиотеки `stopwordsiso` (уже в requirements):

```python
import stopwordsiso as stopwords
STOPWORDS_BY_LANG = {
    "ru": stopwords.stopwords("ru"),
    "en": stopwords.stopwords("en"),
    "de": stopwords.stopwords("de"),
    "it": stopwords.stopwords("it"),
    "es": stopwords.stopwords("es"),
    "fr": stopwords.stopwords("fr"),
}
```

Используется в `qa_metrics.py` для расчёта keyword_usage.

#### 8.2.3. Sentence splitter

Использовать `pysbd` (Pragmatic Sentence Boundary Disambiguation) — работает для 20+ языков:

```python
import pysbd
def get_splitter(language: str):
    return pysbd.Segmenter(language=language, clean=False)
```

Используется в `qa_metrics.py._readability_score`.

#### 8.2.4. Каталог референсов писателей

БД-таблица `style_references` с колонкой `language`. При добавлении референса — указывается язык. При создании автора — фильтруется по языку автора.

**Обязательство разработчику:** заполнить каталог **минимум 3-5 референсов на каждый язык** для первого релиза. Примеры:
- ru: Довлатов, Бродский, Гончарова, Улицкая.
- en: Hemingway, Orwell, Vonnegut, Didion.
- de: Kafka, Böll, Grass, Zeh.
- it: Calvino, Eco, Pavese, Ferrante.
- es: Márquez, Cortázar, Vargas Llosa, Bolaño.
- fr: Camus, Duras, Houellebecq, Ernaux.

Разработчик готовит по 3-5 абзацев текста каждого + через `style_extractor_agent` извлекает стиль и сохраняет в БД.

#### 8.2.5. Настройки поиска картинок

- **Pixabay:** поддерживает `lang` параметр — передавать язык статьи.
- **Unsplash:** только английский — image_keys_agent генерирует ключи на английском (для всех языков статей).
- **Wikimedia:** передавать язык статьи для локализованных названий.

#### 8.2.6. Fact-checking по языкам

- Wikipedia REST API работает для всех 6 языков — использовать `https://{lang}.wikipedia.org/...`.
- Wikidata — универсальный, но с русским покрытием заметно хуже английского. Fallback: если Wikidata пустой — идти в языковую Wikipedia.

#### 8.2.7. Регулярки qa_metrics

Регулярные выражения для чисел + единиц измерения должны учитывать локализации:
- Английский: "1,642 m", "20%", "25-30 million years"
- Русский: "1 642 м", "25–30 млн лет"
- Немецкий: "1.642 m", "25-30 Millionen Jahre"

Реализовать пакет мультиязычных regex-паттернов.

### 8.3. Критерии приёмки многоязычности

- **Обязательно к релизу:** прогон одной статьи на каждом из 6 языков + прохождение QA >= 75.
- **Каталог референсов:** минимум 3 автора на язык.

---

## 9. Fact-checking (обязательный агент)

### 9.1. Цель

Проверить фактические утверждения в статье через внешние базы данных (Wikipedia, Wikidata) и передать отчёт критику для обоснованной оценки factuality.

### 9.2. Место в пайплайне

**Шаг 11** — после Sources Weaver, перед Final QA.

### 9.3. Схема FactCheckReport

```python
class FactStatement(BaseModel):
    text: str                    # исходное предложение из статьи
    type: str                    # "numeric" | "date" | "location" | "name"
    subject: str                 # "Байкал"
    property: Optional[str]      # "глубина"
    value_in_article: str        # "1642 м"

class FactCheckResult(BaseModel):
    statement: FactStatement
    status: str                  # "verified" | "mismatch" | "uncertain"
    external_value: Optional[str]  # что нашли во внешнем источнике
    source_url: Optional[str]
    source_name: Optional[str]     # "Wikipedia (ru)" | "Wikidata"
    confidence: float              # 0.0 - 1.0

class FactCheckReport(BaseModel):
    total_statements: int
    verified: int
    mismatches: int
    uncertain: int
    results: List[FactCheckResult]
    checked_at: datetime
```

### 9.4. Логика работы

#### 9.4.1. Extraction (LLM)

LLM получает markdown статьи и возвращает список атомарных утверждений:

```
Для каждого утверждения:
- text: исходное предложение
- type: numeric | date | location | name
- subject: о ком/чём (главная сущность)
- property: атрибут (для numeric/date)
- value_in_article: цифра/дата/место
```

Минимум 5, максимум 20 утверждений на статью. Приоритет — ключевые факты (главные цифры, даты, ссылки на организации).

#### 9.4.2. Verification (внешние API)

Для каждого утверждения:

**Тип "numeric":**
1. Найти сущность в Wikidata (SPARQL query по label):
   ```sparql
   SELECT ?item ?itemLabel WHERE {
     ?item rdfs:label "Байкал"@ru.
     ?item wdt:P31 wd:Q23397.
   }
   ```
2. Если найден Q-код — запросить свойство:
   ```sparql
   SELECT ?depth ?depthUnit WHERE {
     wd:Q5513 wdt:P4511 ?depth.
   }
   ```
3. Сравнить с value_in_article (с допуском ±5%).

**Тип "date":**
1. Найти сущность в Wikidata.
2. Запросить точную дату (P571 - inception, P585 - point in time и т.п.).
3. Сравнить точно.

**Тип "location":**
1. Найти сущность в Wikidata.
2. Запросить P17 (страна), P131 (административная единица).
3. Проверить упоминание.

**Тип "name":**
1. Найти сущность через search Wikipedia (`/api/rest_v1/page/summary/{title}`).
2. Проверить существование и релевантность.

#### 9.4.3. Fallback strategy

- Если Wikidata не даёт результат — запросить Wikipedia REST API.
- Если Wikipedia не даёт — status="uncertain".
- Никогда не поднимать exception — при ошибке просто status="uncertain".

#### 9.4.4. Кэширование

Все запросы к внешним источникам кэшируются:
- `data/wiki_cache/wikidata/<hash>.json`
- `data/wiki_cache/wikipedia/<lang>/<title>.json`

TTL — 30 дней (факты меняются редко).

### 9.5. Действие при mismatch

Промпт для `final_qa_agent` принимает fact_check_report и:
- Если > 20% mismatches — снижает factuality до 40-50.
- Если 10-20% mismatches — снижает до 60-70.
- Если < 10% — оценка без наказания.

В warnings добавляются конкретные mismatches:
```json
{
  "critical": ["В статье: глубина Байкала 1500 м. По данным Wikidata: 1642 м."],
  ...
}
```

### 9.6. Ограничения

- **Не пытаться исправлять** статью автоматически — только помечать.
- **Не запрашивать факты, не имеющие verifiable сущностей** — например, метафоры, обобщения.
- **Максимум 20 утверждений на статью** — иначе процесс займёт несколько минут.

### 9.7. Оценочные затраты

- **Время:** +30-60 секунд к пайплайну.
- **Стоимость LLM:** +$0.02-0.05 на статью (extraction).
- **Внешние API:** бесплатно (Wikipedia/Wikidata).

---

*Продолжение в части 4 (UI, API, БД)*

---

## 10. UI — детальные спецификации всех экранов

### 10.1. Общая структура интерфейса

**Layout (grid):**
- Слева: боковая панель `nav-sidebar` (200px, всегда видна) — три шага пайплайна.
- Сверху: top bar с логотипом, статусом текущей генерации, счётчиками стоимости.
- Справа от top bar (только на Главной): кнопки Сайты / Аналитика / История / Настройки.
- Основная область: страница по маршруту.

### 10.2. Роутинг

```
/            → Главная (форма создания статьи)
/write       → Написание (мониторинг активной генерации)
/result/:id  → Результат готовой статьи
/history     → История всех статей
/sites       → Управление сайтами (+ авторы + референсы)
/analytics   → Аналитика
/settings    → Настройки
/login       → Форма логина (basic auth)
```

### 10.3. Экран "Главная" (/)

Форма создания статьи (см. FR-04). Разделена на секции:
- Основные параметры (тема, ключи, сайт, автор).
- Стратегия объёма (радио 4 варианта).
- Параметры генерации (язык, гео, интент, тип, сложность, стиль).
- Ограничения (запрещённые слова, обязательные элементы).
- Настройки пайплайна (пауза, force refresh SERP).

Кнопки:
- "Проверить данные" — валидация без запуска.
- "Запустить пайплайн" — валидация + POST на `/api/pipeline/run`.

Валидация:
- Клиентская — обязательные поля, форматы.
- Серверная — Pydantic ArticleInput.
- Ошибки показываются inline под полем.

### 10.4. Экран "Написание" (/write)

Активен во время генерации. Показывает realtime-прогресс.

**Восстановление после перезагрузки страницы:** при открытии `/write` (в т.ч. после перезагрузки) клиент сначала выполняет `GET /api/pipeline/{id}/status` и `GET /api/pipeline/{id}/events` для восстановления состояния (лог, диалог агентов, прогресс), затем подключается к WebSocket. Дубликаты событий (полученные и через REST, и через WS) дедуплицируются по `event_id`.

**Параллельные генерации:** одновременно может выполняться до 2 пайплайнов (лимит Celery concurrency). Экран `/write` показывает генерацию, выбранную параметром `?id={article_id}`; без параметра — последнюю запущенную. Переключение между активными генерациями — через список «В работе» на экране «История» (статьи с нетерминальным статусом отображаются вверху с индикатором). При запуске третьего пайплайна задача ставится в очередь Celery (статус `created`, UI показывает «В очереди»).

**Boxes:**

1. **Hero-статус (вверху):**
   - Крупный текст: текущий шаг ("Шаг 5/13: Outline").
   - Progress bar (13 шагов).
   - Стоимость: "$0.023 потрачено".
   - Время: "2:15 с начала генерации".

2. **Список шагов (левый sidebar):**
   - 13 пунктов.
   - Иконка: ⏳ выполняется / ✓ готово / ✗ ошибка / ○ ожидание.
   - Для каждого — время выполнения.

3. **Секции (в left sidebar после outline):**
   - Список секций outline.
   - Для каждой — статус (writer / critic / editor) + количество итераций.

4. **Вкладки (основная область):**
   - **Лог** — построчный лог с временем.
   - **Диалог агентов** — раскрывающиеся блоки с промптом и ответом каждого LLM-вызова.
   - **Результат** — заполняется в конце.

5. **Действия:**
   - "Остановить" — POST `/api/pipeline/{id}/stop`.

### 10.5. Review-панель (модальное окно во время паузы)

Открывается автоматически при получении WebSocket-события `review_ready`.

**Layout:** двухколоночный.

**Левая колонка (сводка конкурентов):**
- Word count avg / min / max (после trimmed mean).
- H2 count avg / min / max.
- Список общих H2 конкурентов (top-10 по частоте).
- Must-have topics (checkable).
- Content gaps (checkable — можно включить в outline).

**Правая колонка (outline editor):**
- Suggested archetype с description.
- Alternatives (radio) — переключение архетипа.
- H1 (input).
- Список секций (drag-n-drop reorderable):
  - Для каждой: title (input), level (H2/H3 switch), target_word_count (number), кнопка удалить.
- "Добавить секцию" (создаёт новую пустую).
- "Добавить из точек роста" (для отмеченных gap).
- Сумма total_word_count.

**Внизу:**
- "Отменить генерацию" (модальное подтверждение).
- "Продолжить генерацию" — POST `/api/pipeline/{id}/resume`.

### 10.6. Экран "Результат" (/result/:id)

Открывается автоматически по завершении пайплайна + доступен из "Истории".

**Секции:**

1. **QA-панель:**
   - Круг со score (85/100).
   - Статус: PASS / PASS WITH WARNINGS / FAIL.
   - Рекомендация (текст от LLM).
   - Раскрывающийся блок с детализацией 9 критериев.
   - Три блока предупреждений:
     - 🔴 Критические — красная рамка.
     - 🟡 Средние — жёлтая рамка.
     - 🟢 Незначительные — серая рамка.

2. **Метаданные:**
   - Slug (копирабельно).
   - Meta title (60 символов).
   - Meta description (160 символов).
   - Теги (chips).
   - Категория.

3. **Информация:**
   - Стоимость: $0.045.
   - Время генерации: 4:32 (без пауз).
   - Модели использованы: Sonnet, Haiku.

4. **Просмотр статьи:**
   - Переключатель Markdown / Rendered.
   - В rendered — статья с картинками, форматированием.

5. **Действия:**
   - "Копировать markdown".
   - "Скачать архив" (zip с article.md + images).
   - "Опубликовать в WordPress" (если настроено).

### 10.7. Экран "История" (/history)

Список статей. Каждая строка:
- Дата, тема, сайт.
- Автор, статус, score, стоимость.
- Кнопка "Открыть" → /result/:id.

Фильтры (левая панель):
- Сайт (multiselect).
- Статус (multiselect).
- Даты (диапазон).
- Минимальный score.
- Показывать/скрывать тестовые.

Сортировка: по дате (desc default), по score, по стоимости.

Пагинация: по 20 на страницу.

Действия над выбранными:
- Экспорт в CSV.
- Массовое удаление.

### 10.8. Экран "Сайты" (/sites)

Список сайтов в виде карточек. Каждая карточка:
- Домен, название.
- Ниша, is_test.
- Статистика: количество статей, средний QA, средняя стоимость.
- Клик по карточке → детальный вид сайта.

**Детальный вид сайта:**
- Основная информация (редактируемая).
- Раздел "Авторы": список авторов с action-кнопками (создать, редактировать, деактивировать).
- Раздел "Референсы стиля" (если сайт использует референсы): список с extracted_style.

Кнопки:
- "+ Создать сайт".
- "+ Создать автора" (в детальном виде сайта).

### 10.9. Экран "Аналитика" (/analytics)

Отчёты и графики:
- Total статей / средний QA / средняя стоимость / общий бюджет.
- Distribution по статусам (pie chart).
- Distribution по сайтам (bar chart).
- Тренд по неделям (line chart).
- Топ авторов по QA-score.
- Топ статей по стоимости.

Фильтры: даты, сайты, авторы.

Экспорт в CSV.

### 10.10. Экран "Настройки" (/settings)

- **API-ключи** (Anthropic, Pixabay, Unsplash, XMLStock URL): поля ввода. Существующие значения не показываются — только индикатор «задан / не задан» и число ключей для мультиключевых провайдеров. Ввод нового значения перезаписывает старое.
- **WordPress:** настраивается per-site на экране «Сайты» (URL, user, application password).
- **Управление кэшем:** кнопки очистки (SERP / agent / image_keys / translation / wiki).
- **Информация о версии.**

**Хранение настроек — таблица `app_settings`:**

```sql
CREATE TABLE app_settings (
    key         TEXT PRIMARY KEY,      -- 'anthropic_api_key', 'pixabay_api_keys', ...
    value       TEXT NOT NULL,         -- зашифровано Fernet (ключ SETTINGS_ENCRYPTION_KEY из .env)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Приоритет чтения:** значение из БД → если нет, значение из `.env`. Это позволяет запустить приложение с ключами в `.env` (первый старт), а дальше управлять ими из UI без рестарта контейнеров.

**Применение без рестарта:** worker читает актуальные значения из БД в начале каждой задачи `run_pipeline` (не кэширует в памяти процесса). Backend читает при каждом обращении к внешнему API.

В `.env` остаются только: `DATABASE_URL`, `REDIS_URL`, `SETTINGS_ENCRYPTION_KEY`, `WP_ENCRYPTION_KEY`, `BASIC_AUTH_USERNAME`, `BASIC_AUTH_PASSWORD`.

**API:**

```
GET /api/settings   → {anthropic_key_set: bool, pixabay_keys_count: int,
                       unsplash_keys_count: int, xmlstock_url: str, ...}
                       (сами ключи НЕ возвращаются, только статус «задан/не задан»)
PUT /api/settings   → 204  (тело: {key_name: value, ...})
```

### 10.11. Общие требования к UI

- **Тёмная тема** (Catppuccin-inspired) с возможностью переключения на светлую.
- **Адаптивность:** работает на десктопе (1200+ px), поддержка planшетов (768+), мобильных (базовая).
- **Loading states:** для всех async-действий — spinner или skeleton.
- **Error states:** понятные сообщения об ошибках.
- **Toast notifications:** для успехов/ошибок (использовать библиотеку типа react-hot-toast).
- **Клавиатурная навигация:** Escape закрывает модальные окна.

---

## 11. API — REST + WebSocket

### 11.1. Основные принципы

- **Base URL:** `/api`.
- **Формат:** JSON.
- **Аутентификация:** HTTP Basic Auth. Логин/пароль из .env.
- **Ошибки:** HTTP 4xx с JSON `{"detail": "текст ошибки"}`.
- **Валидация:** Pydantic-схемы.

### 11.2. REST endpoints

#### 11.2.1. Sites

```
GET    /api/sites                       → List[Site]
POST   /api/sites                       → Site (создать)
GET    /api/sites/{domain}              → Site
PUT    /api/sites/{domain}              → Site (обновить)
DELETE /api/sites/{domain}              → 204
GET    /api/sites/{domain}/stats        → SiteStats (кол-во статей, avg QA, cost)
```

#### 11.2.2. Authors

```
GET    /api/sites/{domain}/authors       → List[Author]
POST   /api/sites/{domain}/authors       → Author
GET    /api/authors/{author_id}          → Author
PUT    /api/authors/{author_id}          → Author
DELETE /api/authors/{author_id}          → 204 (soft-delete)
```

#### 11.2.3. Style references

```
GET    /api/references                   → List[StyleReference]  (с filter по language)
POST   /api/references                   → StyleReference (создать, извлекает стиль автоматически)
GET    /api/references/{reference_id}    → StyleReference
DELETE /api/references/{reference_id}    → 204
POST   /api/references/extract           → {extracted_style, extracted_tone, extracted_age_image}
                                           (extract без сохранения — для preview)
```

#### 11.2.4. Niches и Archetypes (только чтение)

```
GET    /api/niches                       → List[Niche]
GET    /api/archetypes                   → List[Archetype]     (filter по niche_id)
GET    /api/archetypes/suggest           → {suggested_archetype_id, alternatives}
                                           (query params: article_title, main_keyword, niche_id)
```

#### 11.2.5. Articles

```
GET    /api/articles                     → List[Article]  (filter: site, status, dates, min_score)
GET    /api/articles/{article_id}        → Article с метаданными
GET    /api/articles/{article_id}/result → {qa_result, final_package, article_markdown, images_urls}
GET    /api/articles/{article_id}/archive → binary (zip)
DELETE /api/articles/{article_id}        → 204
```

`DELETE` удаляет запись из БД (каскадно pipeline_steps, sections, archetype_picks, fact_check_results) **и папку** `data/articles/<slug>_<id>/` с диска. Кэши (serp_cache, agent_cache) не затрагиваются.

#### 11.2.6. Pipeline

```
POST   /api/pipeline/run                 → {article_id, ws_url}  (тело: ArticleInput)
POST   /api/pipeline/{article_id}/stop   → 204
POST   /api/pipeline/{article_id}/resume → 204  (тело: отредактированный Outline)
GET    /api/pipeline/{article_id}/status → {status, current_step, elapsed_time, ...}
GET    /api/pipeline/{article_id}/events → {events: [...]}
```

`GET .../events` возвращает полную историю событий пайплайна (log_entry, step_started/finished, prompt_captured, section_update, cost_update) в хронологическом порядке. События по ходу генерации пишутся worker'ом в Redis (list `pipeline:events:{article_id}`, TTL 24 ч) параллельно с pub/sub. Для завершённых статей промпты читаются с диска (`data/articles/<dir>/prompts/`). Каждое событие содержит `event_id` — монотонный счётчик в рамках пайплайна (см. 11.3.2) — для дедупликации с WebSocket-потоком.

#### 11.2.7. Analytics

```
GET /api/analytics/overview               → {total, avg_qa, total_cost, ...}
GET /api/analytics/by-site               → List[{site, count, avg_qa, cost}]
GET /api/analytics/trend                 → List[{week, count, avg_qa}]
GET /api/analytics/top-authors           → List[{author, count, avg_qa}]
GET /api/analytics/export.csv            → binary
```

#### 11.2.8. Cache management

```
DELETE /api/cache/serp                   → 204
DELETE /api/cache/agent                  → 204
DELETE /api/cache/image_keys             → 204
DELETE /api/cache/translation            → 204
DELETE /api/cache/wiki                   → 204
```

#### 11.2.9. WordPress

```
POST /api/wordpress/publish              → {post_id, url}  (тело: {article_id, status: 'draft' | 'publish'})
GET  /api/wordpress/status                → {connected: bool, url}
```

### 11.3. WebSocket protocol

#### 11.3.1. Endpoint

```
WS /ws/pipeline/{article_id}
```

Аутентификация через query string: `?token=...` (basic auth encoded).

#### 11.3.2. События от сервера к клиенту

Все события — JSON. Формат:

```json
{
  "type": "event_type",
  "event_id": 42,
  "timestamp": "2026-07-03T14:22:00Z",
  "data": {...}
}
```

`event_id` — монотонный счётчик в рамках пайплайна. Используется клиентом для дедупликации событий, полученных и через `GET /api/pipeline/{id}/events`, и через WebSocket.

**Типы событий:**

**`step_started`** — начало шага:
```json
{"type": "step_started", "data": {"step_name": "brief_generation", "step_number": 4, "total_steps": 13}}
```

**`step_finished`** — окончание шага:
```json
{"type": "step_finished", "data": {"step_name": "brief_generation", "duration_seconds": 12.5, "success": true}}
```

**`log_entry`** — строка лога:
```json
{"type": "log_entry", "data": {"level": "info", "message": "Кэш-хит — пропускаем LLM-вызов"}}
```

**`prompt_captured`** — сохранён промпт агента:
```json
{"type": "prompt_captured", "data": {"step_name": "brief_generation", "prompt": "...", "response": "..."}}
```

**`section_update`** — обновление статуса секции:
```json
{"type": "section_update", "data": {"section_id": "s1", "status": "writer_2", "word_count": 220}}
```

**`cost_update`** — обновление счётчика стоимости:
```json
{"type": "cost_update", "data": {"article": 0.023, "session": 0.145, "last_call": 0.008, "total": 12.34}}
```

**`review_ready`** — пауза для ревью:
```json
{
  "type": "review_ready",
  "data": {
    "competitor_summary": {...},
    "content_gaps_filtered": [...],
    "archetype_suggestion": {...},
    "outline": {...}
  }
}
```

**`finished`** — пайплайн завершён:
```json
{"type": "finished", "data": {"qa_result": {...}, "final_package": {...}}}
```

**`error`** — ошибка:
```json
{"type": "error", "data": {"message": "...", "step_name": "..."}}
```

**`aborted`** — пайплайн остановлен пользователем или системой:
```json
{"type": "aborted", "data": {"reason": "stopped_by_user"}}
```

#### 11.3.3. События от клиента к серверу

- Опционально: ping-сообщения `{"type": "ping"}` — сервер отвечает `{"type": "pong"}`.

---

## 12. Схема БД (PostgreSQL)

### 12.1. Таблицы

#### 12.1.1. niches

```sql
CREATE TABLE niches (
    niche_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,           -- локализованное название
    description  TEXT
);
```

Seed: travel, home, auto, lifestyle, pets, garden, utility (+ можно расширять).

#### 12.1.2. archetypes

```sql
CREATE TABLE archetypes (
    archetype_id     TEXT PRIMARY KEY,
    niche_id         TEXT NOT NULL REFERENCES niches(niche_id),
    name             TEXT NOT NULL,
    description      TEXT,
    intent_triggers  TEXT[]
);
```

Seed: 30+ архетипов по всем нишам.

#### 12.1.3. sites

```sql
CREATE TABLE sites (
    domain            TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    niche_id          TEXT REFERENCES niches(niche_id),
    is_test           BOOLEAN NOT NULL DEFAULT FALSE,
    wordpress_url     TEXT,
    wordpress_user    TEXT,
    wordpress_password TEXT,             -- зашифровано
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 12.1.4. style_references

```sql
CREATE TABLE style_references (
    reference_id          TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    language              TEXT NOT NULL,       -- ru, en, de, it, es, fr
    geo                   TEXT NOT NULL,
    niche_tags            TEXT[],
    notes                 TEXT,
    reference_text        TEXT,                -- исходный текст-референс
    extracted_style       TEXT,
    extracted_tone        TEXT,
    extracted_age_image   TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_style_references_language ON style_references(language);
CREATE INDEX idx_style_references_niche_tags ON style_references USING GIN(niche_tags);
```

#### 12.1.5. authors

```sql
CREATE TABLE authors (
    author_id       TEXT PRIMARY KEY,
    site_domain     TEXT NOT NULL REFERENCES sites(domain),
    name            TEXT NOT NULL,
    character       TEXT,
    tone            TEXT,
    age_image       TEXT,
    niche_id        TEXT REFERENCES niches(niche_id),
    reference_id    TEXT REFERENCES style_references(reference_id),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_authors_site_domain ON authors(site_domain);
```

#### 12.1.6. articles

```sql
CREATE TABLE articles (
    article_id      UUID PRIMARY KEY,
    site_domain     TEXT NOT NULL REFERENCES sites(domain),
    author_id       TEXT REFERENCES authors(author_id),
    archetype_id    TEXT REFERENCES archetypes(archetype_id),
    title           TEXT,
    main_keyword    TEXT,
    language        TEXT NOT NULL,
    status          TEXT NOT NULL,
    qa_status       TEXT,
    qa_score        INTEGER,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    generation_time_seconds INTEGER,      -- без пауз
    input_data      JSONB,                 -- ArticleInput
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_articles_site_domain ON articles(site_domain);
CREATE INDEX idx_articles_created_at ON articles(created_at DESC);
CREATE INDEX idx_articles_status ON articles(status);
```

#### 12.1.7. pipeline_steps

```sql
CREATE TABLE pipeline_steps (
    id             SERIAL PRIMARY KEY,
    article_id     UUID REFERENCES articles(article_id) ON DELETE CASCADE,
    step_name      TEXT NOT NULL,
    step_number    INTEGER,
    status         TEXT NOT NULL,       -- running | done | failed | skipped_cache
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    duration_ms    INTEGER,
    error_message  TEXT,
    tokens_in      INTEGER,
    tokens_out     INTEGER,
    cost_usd       NUMERIC(10,6)
);

CREATE INDEX idx_pipeline_steps_article_id ON pipeline_steps(article_id);
```

#### 12.1.8. sections

```sql
CREATE TABLE sections (
    id          SERIAL PRIMARY KEY,
    article_id  UUID REFERENCES articles(article_id) ON DELETE CASCADE,
    section_id  TEXT NOT NULL,
    title       TEXT,
    status      TEXT NOT NULL,
    iterations  INTEGER DEFAULT 0,       -- сколько раз Writer перегенерировал
    word_count  INTEGER DEFAULT 0
);

CREATE INDEX idx_sections_article_id ON sections(article_id);
```

#### 12.1.9. archetype_picks

```sql
CREATE TABLE archetype_picks (
    id                      SERIAL PRIMARY KEY,
    article_id              UUID REFERENCES articles(article_id) ON DELETE CASCADE,
    suggested_archetype_id  TEXT REFERENCES archetypes(archetype_id),
    chosen_archetype_id     TEXT REFERENCES archetypes(archetype_id),
    matched                 BOOLEAN NOT NULL,
    niche_id                TEXT REFERENCES niches(niche_id),
    intent                  TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### 12.1.10. fact_check_results (новая)

```sql
CREATE TABLE fact_check_results (
    id                SERIAL PRIMARY KEY,
    article_id        UUID REFERENCES articles(article_id) ON DELETE CASCADE,
    total_statements  INTEGER,
    verified          INTEGER,
    mismatches        INTEGER,
    uncertain         INTEGER,
    results_json      JSONB,               -- полный FactCheckReport
    checked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fact_check_article_id ON fact_check_results(article_id);
```

### 12.2. Материализованные view для аналитики

Для быстрой аналитики создать материализованные view:

```sql
CREATE MATERIALIZED VIEW mv_articles_by_site_month AS
SELECT
    site_domain,
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*) AS total,
    AVG(qa_score) AS avg_qa,
    SUM(cost_usd) AS total_cost
FROM articles
WHERE status = 'completed'
GROUP BY site_domain, DATE_TRUNC('month', created_at);

REFRESH MATERIALIZED VIEW mv_articles_by_site_month;
```

Обновление: cron/celery beat раз в час.

### 12.3. Миграции

Использовать Alembic для миграций.

Первая миграция создаёт все таблицы + seed niches/archetypes.

Последующие миграции — при изменении схемы.

---

*Продолжение в части 5 (Docker, промпты, критерии приёмки, риски, out of scope)*

---

## 13. Схемы данных (Pydantic)

Все схемы — Pydantic 2.

### 13.1. ArticleInput

```python
class ArticleInput(BaseModel):
    # системные
    article_id:         str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at:         datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pipeline_version:   str = "v1"
    prompt_set_version: str = "v1"

    # основные
    site_domain:        str = Field(default="example.net", min_length=3, max_length=253)
    author_id:          Optional[str] = None
    article_title:      str = Field(..., min_length=5, max_length=300)
    main_keyword:       str = Field(..., min_length=2, max_length=300)
    secondary_keywords: List[str] = Field(..., min_length=1)

    # длина
    length_strategy:    str = Field(default="match_top",
                                    pattern=r"^(shorter_top|match_top|longer_top|custom)$")
    target_word_count:  Optional[int] = Field(default=None, ge=300, le=10000)

    # язык
    language:           str = Field(..., pattern=r"^(ru|en|de|it|es|fr)$")
    geo:                str = Field(..., min_length=2, max_length=150)

    # тип статьи
    intent:             str = Field(..., pattern=r"^(informational|how_to)$")
    article_type:       str = Field(..., pattern=r"^(informational|how_to)$")
    difficulty:         str = Field(..., pattern=r"^(easy|medium|hard)$")
    style_archetype:    str = Field(..., pattern=r"^(expert_clear|friendly_practical|calm_analytical|editorial_neutral)$")

    # ограничения
    forbidden_words:    List[str] = Field(default_factory=list)
    required_elements:  List[str] = Field(...)
    optional_notes:     Optional[str] = Field(default=None, max_length=5000)

    # настройки пайплайна
    review_outline:        bool = True   # пауза после шага 5 для ручного ревью структуры
    enable_section_critic: bool = True   # цикл Writer -> Critic -> Editor для каждой секции
    force_refresh_serp:     bool = False

    # SERP
    serp_json_path:  Optional[str] = None
    manual_sources:  Optional[List[str]] = None
```

Валидаторы:
- `target_word_count` обязателен если `length_strategy == "custom"`.
- `required_elements` — подмножество {faq, quick_answer, table, list, conclusion, weaved_sources}. Элемент `sources_block` (отдельный блок источников в конце статьи) не поддерживается — заменён на `weaved_sources`.
- Списки дедуплицируются и очищаются от пустых.

### 13.2. CompetitorAnalysisReport

```python
class WordCountRange(BaseModel):
    min: int = 0
    avg_trimmed: float = 0.0    # trimmed mean
    max: int = 0
    per_page: List[int] = []

class CommonH2Title(BaseModel):
    title: str
    frequency: int

class ContentGap(BaseModel):
    title: str
    description: str
    after_section: str = ""
    word_count: int = 200

class DataSensitivity(BaseModel):
    has_volatile_data: bool = False    # в теме есть быстро устаревающие данные (цены, расписания, курсы)
    has_precise_numbers: bool = False  # конкуренты оперируют точными цифрами (глубина, высота, даты)
    notes: str = ""

class CompetitorAnalysisReport(BaseModel):
    search_intent:      str = "informational"
    content_type:       str = "guide"
    word_count_range:   WordCountRange
    h2_count_range:     WordCountRange     # такая же схема
    common_h2_titles:   List[CommonH2Title]
    must_have_topics:   List[str]
    optional_topics:    List[str]
    content_gaps:       List[ContentGap]
    data_sensitivity:   DataSensitivity = DataSensitivity()
    tone:               str = "neutral_informational"
    target_audience:    str = ""
    raw_report:         str = ""
```

### 13.3. Brief

```python
class KeywordsBlock(BaseModel):
    main: str = ""
    secondary: List[str] = []

class DataHandlingRules(BaseModel):
    avoid_exact_dates: bool = False
    use_approximate_language: bool = False

class Brief(BaseModel):
    goal:                str = ""
    search_intent:       str = "informational"
    target_audience:     str = ""
    content_archetype:   str = "guide"
    tone:                str = "neutral_informational"
    style_requirements:  List[str] = []
    must_cover:          List[str] = []
    must_not_cover:      List[str] = []
    structure_guidelines: List[str] = []
    word_count_target:   int = 1200
    word_count_range:    WordCountRange
    keywords:            KeywordsBlock
    lsi_keywords:        List[str] = []
    required_elements:   List[str] = []
    forbidden_words:     List[str] = []
    data_handling_rules: DataHandlingRules
    raw_brief:           str = ""
```

### 13.4. Outline

```python
class SectionSpec(BaseModel):
    section_id:        str
    title:             str
    level:             str = "H2"        # H2 | H3
    purpose:           str = ""
    target_word_count: int = 200
    keywords:          List[str] = []
    must_cover:        List[str] = []

class FaqSection(BaseModel):
    enabled:   bool = False
    questions: List[str] = []

class Outline(BaseModel):
    h1:          str = ""
    sections:    List[SectionSpec]
    faq_section: FaqSection = FaqSection()
```

### 13.5. Section pipeline

```python
class SectionAttempt(BaseModel):
    section_id: str
    iteration:  int
    author:     str
    text:       str
    summary:    Optional[str]           # <!-- SUMMARY: ... -->
    tokens_in:  int
    tokens_out: int
    cost_usd:   float

class CriticFeedback(BaseModel):
    overall_score: int          # 0-100
    per_criterion: dict
    issues:        List[str]
    suggestions:   List[str]

class SectionFinal(BaseModel):
    section_id: str
    title:      str = ""
    content:    str = ""
    iterations: int = 1
```

### 13.6. FullDraft

```python
class FullDraft(BaseModel):
    h1:               str = ""
    content_markdown: str = ""
    sections:         List[SectionFinal]
    word_count:       int = 0
    section_count:    int = 0
```

### 13.7. FactCheckReport

См. раздел [9.3](#93-схема-factcheckreport).

### 13.8. QAResult

```python
class CriteriaScores(BaseModel):
    brief_alignment:  float = 0.0
    intent_coverage:  float = 0.0
    keyword_usage:    float = 0.0
    lsi_coverage:     float = 0.0
    factuality:       float = 0.0
    structure:        float = 0.0
    readability:      float = 0.0
    length_control:   float = 0.0
    completeness:     float = 0.0

class QAWarnings(BaseModel):
    critical: List[str] = []
    medium:   List[str] = []
    minor:    List[str] = []

class QAResult(BaseModel):
    status:          str                # 'pass' | 'pass_with_warnings' | 'fail'
    score:           int                # 0-100
    criteria_scores: CriteriaScores
    warnings:        QAWarnings
    fail_reasons:    List[str]
    recommendation:  str
```

### 13.9. FinalPackage

```python
class FaqItem(BaseModel):
    question: str
    answer:   str

class SchemaBlock(BaseModel):
    type: str = "FAQPage"
    data: dict

class FinalPackage(BaseModel):
    article_id:                 str
    slug:                       str
    meta_title:                 str
    meta_description:           str
    article_markdown:           str
    faq:                        List[FaqItem]
    schema_data:                SchemaBlock
    category:                   str
    tags:                       List[str]
    internal_links_suggestions: List[str]
```

---

## 14. Внешние интеграции

### 14.1. Anthropic Claude API

- **SDK:** `anthropic` Python (>=0.34).
- **Модели:**
  - Claude Sonnet 4.6 — основная (для writer, critic, editor, brief, outline, competitor_analysis, faq, sources_weaver, fact_checker, final_qa, metadata).
  - Claude Haiku 4.5 — для дешёвых задач (lsi_agent, image_keys_agent, archetype_picker_agent, style_extractor_agent).
- **API ключ:** `ANTHROPIC_API_KEY` в .env.
- **Retry:** exponential backoff при 429/500 (см. `retry_service`).
- **Стоимость:** одна статья — $0.05-0.15.

### 14.2. XMLStock SERP API

- **URL:** self-hosted (`http://95.217.108.20:8085/api/v1/parsers/xmlstock/serp`).
- **Метод:** GET.
- **Query params:** `q` (main_keyword), `geo`, `hl` (language).
- **Ответ:** JSON `{items: [{url, title, description}, ...]}`.
- **Далее:** для каждого URL — HTTP GET, парсинг через readability-lxml.

### 14.3. Pixabay API

- **URL:** `https://pixabay.com/api/`.
- **Auth:** API key в query string (`&key=...`).
- **Ротация:** 10 ключей через запятую в `PIXABAY_API_KEYS`.
- **Query params:** `q` (searchquery), `image_type=photo`, `orientation=horizontal`, `min_width=1280`, `lang` (язык).
- **Rate limit:** 5000 запросов/час на ключ.

### 14.4. Unsplash API

- **URL:** `https://api.unsplash.com/search/photos`.
- **Auth:** Access Key в header `Authorization: Client-ID {access_key}`.
- **Ротация:** 10 ключей в `UNSPLASH_ACCESS_KEYS`.
- **Query params:** `query` (searchquery), `orientation=landscape`.
- **Rate limit:** 50 запросов/час на demo, 5000/час на production.

### 14.5. Wikimedia Commons

- **URL:** `https://commons.wikimedia.org/w/api.php`.
- **Auth:** не требуется.
- **Query params:** `action=query`, `list=search`, `srnamespace=6` (File namespace), `srsearch={query}`, `format=json`.
- **Далее:** получить URL картинки через `imageinfo` API.

### 14.6. Wikipedia REST API (для fact-checker)

- **URL:** `https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}`.
- **Auth:** не требуется.
- **Rate limit:** нет.
- **Кэш:** 30 дней.

### 14.7. Wikidata SPARQL

- **URL:** `https://query.wikidata.org/sparql`.
- **Формат:** SPARQL query.
- **Auth:** не требуется.
- **Rate limit:** есть, но не критично для 20 фактов/статью.
- **User-Agent:** обязателен (иначе блокируют).

### 14.8. WordPress REST API

- **URL:** конфигурируется по сайту (`sites.wordpress_url`).
- **Auth:** Basic Auth с Application Password.
- **Endpoints:**
  - `POST /wp-json/wp/v2/media` — загрузка картинки.
  - `POST /wp-json/wp/v2/posts` — создание поста.

---

## 15. Публикация в WordPress

### 15.1. Настройка

Для каждого сайта в БД (`sites` table):
- `wordpress_url` — например `https://kroppa.ru`.
- `wordpress_user` — WP username.
- `wordpress_password` — Application Password (зашифрован, см. 15.4).

### 15.2. Процесс публикации

Пользователь на странице результата жмёт "Опубликовать в WordPress":

1. Backend получает `article_id`.
2. Загружает готовый markdown + список локальных картинок.
3. Для каждой картинки:
   - Загружает в WP через `POST /wp-json/wp/v2/media` (multipart form).
   - Получает URL картинки в WP.
   - Заменяет локальный путь в markdown на URL WP.
4. Создаёт пост:
   ```json
   POST /wp-json/wp/v2/posts
   {
     "title": "meta_title",
     "content": "<markdown converted to HTML>",
     "excerpt": "meta_description",
     "status": "draft",
     "categories": [category_id],
     "tags": [tag_ids],
     "meta": {
       "yoast_wpseo_title": "meta_title",
       "yoast_wpseo_metadesc": "meta_description"
     }
   }
   ```
5. Возвращает `{post_id, url}` в UI.

### 15.3. Конверсия markdown → HTML

Использовать библиотеку `markdown` (Python) или `marked` (клиентский). Расширения:
- fenced_code
- tables
- toc
- footnotes

### 15.4. Шифрование WP паролей

WP passwords хранятся в БД зашифрованными:
- Ключ шифрования — `WP_ENCRYPTION_KEY` в .env.
- Использовать `cryptography.fernet.Fernet`.

### 15.5. Ошибки

- WP недоступен — таймаут 30 сек, retry 2 раза, при неудаче — ошибка в UI.
- Auth failure — 401, ошибка в UI.
- Категория не найдена — создать автоматически.

---

## 16. Аналитика и статистика

### 16.1. Метрики

**По статьям:**
- Total articles.
- Total by status (completed, pass_with_warnings, failed, stopped).
- Average QA score.
- Distribution QA scores (histogram).
- Total cost USD.
- Average cost per article.

**По сайтам:**
- Articles per site.
- Average QA per site.
- Cost per site.

**По авторам:**
- Articles per author.
- Average QA per author.

**Тренды:**
- Weekly / monthly трафик генерации.
- Тренд QA score во времени.
- Тренд стоимости.

**По архетипам:**
- Использование архетипов (какие используются чаще).
- Success rate по архетипам.
- Match rate: как часто suggested = chosen.

**По времени:**
- Average generation time.
- Median generation time.

### 16.2. Realtime vs агрегированные

- Realtime: последние 100 статей + текущий счётчик стоимости в session.
- Агрегированные: через materialized views, обновляемые раз в час.

### 16.3. Экспорт

CSV с колонками:
`article_id, created_at, site_domain, author_name, title, main_keyword, language, status, qa_score, cost_usd, generation_time_seconds`.

---

## 17. Кэширование и оптимизации

### 17.1. Кэши

| Кэш | Место | Ключ | TTL |
|---|---|---|---|
| SERP | `data/serp_cache/<hash>.json` | main_keyword+geo+language | 7 дней |
| Agent | `data/agent_cache/<agent>/<hash>.json` | agent+title+keyword+secondary | без TTL |
| Image keys | `data/image_keys_cache.json` | main_keyword | без TTL |
| Translation | `data/translation_cache.json` | text+src+dst | без TTL |
| Wiki | `data/wiki_cache/<source>/<key>.json` | Q-code или title | 30 дней |
| Extracted styles | `style_references.extracted_*` в БД | reference_id | до deactive |

### 17.2. Инвалидация

- Через UI (Настройки).
- Через API (`DELETE /api/cache/{type}`).
- `force_refresh_serp=True` в ArticleInput — обходит SERP-кэш.

### 17.3. Redis кэш

Использовать Redis для быстрого realtime-кэша:
- Активные генерации (pipeline статус).
- Session cost counter.
- WebSocket subscription channels.

TTL: 24 часа для сессионных данных.

---

## 18. Самообучение приложения

Anthropic не даёт fine-tuning через публичный API, поэтому "самообучение" в приложении реализуется через **обучение системы использованию LLM** (не самой LLM).

Разработчику предлагается **выбрать одну из четырёх стратегий** для первого релиза. Остальные — задел на будущее.

### 18.1. Стратегия A: Автотюнинг параметров пайплайна по QA-фидбеку

**Как работает:**
- Собирается статистика по прогонам: `(agent, temperature, max_tokens, prompt_version) → avg_qa_score`.
- Раз в неделю — анализ: какие параметры дают статистически более высокий score.
- Автоматическая корректировка параметров в config (или через админ-панель предложение изменений).

**Плюсы:** самое лёгкое в реализации. Без внешних баз.

**Минусы:** требует большого объёма данных (сотни статей), чтобы статистика была значима.

### 18.2. Стратегия B: База проверенных фактов

**Как работает:**
- После каждой статьи с score >= 85 — LLM извлекает фактические утверждения (что подтверждено fact_checker'ом).
- Утверждения сохраняются в БД: `(subject, property, value, source)`.
- При следующей статье на смежную тему — Writer получает эти факты как контекст.

**Плюсы:** снижает галлюцинации, статьи становятся точнее.

**Минусы:** требует чёткой доменной модели (что считать "смежной темой").

### 18.3. Стратегия C: Каталог успешных outline

**Как работает:**
- Outline статьей с QA >= 85 сохраняются в отдельный каталог (in-memory + Postgres).
- При новой статье — outline_agent видит примеры успешных outline на близкие темы (через vector similarity в теме).
- Модель имитирует успешные структуры.

**Плюсы:** реализуемо. Может значимо улучшить структурирование.

**Минусы:** нужен vector similarity search (pgvector extension).

### 18.4. Стратегия D: RAG (Retrieval-Augmented Generation)

**Как работает:**
- Все сгенерированные статьи + внешние авторитетные источники индексируются в векторной БД (pgvector или Chroma).
- При генерации новой статьи Writer получает релевантные chunks из индекса как контекст.
- Fact-checker тоже использует индекс — сначала проверяет по внутреннему индексу, потом обращается к Wikipedia.

**Плюсы:** самый мощный подход. Плавно улучшает качество с ростом базы.

**Минусы:** самый сложный. Требует embedding-модели (OpenAI embeddings или sentence-transformers), pgvector, оптимизации поиска.

### 18.5. Выбранная стратегия

**Первый релиз реализует Стратегию C** (каталог успешных outline). Стратегии A, B, D — в roadmap, реализация не требуется.

Минимальный объём реализации C:
- Расширение Postgres: `CREATE EXTENSION vector;` (pgvector, образ `pgvector/pgvector:pg15` в docker-compose вместо `postgres:15`).
- Таблица `successful_outlines (id, article_id, topic_embedding vector(384), outline_json JSONB, qa_score, language, niche_id, created_at)`.
- Embedding — локальная модель `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dim, бесплатно, без внешних API, поддерживает все 6 языков). Вычисляется от `article_title + main_keyword`.
- После завершения статьи с QA >= 85 — outline сохраняется в каталог.
- Перед вызовом outline_agent — поиск top-3 похожих outline (`ORDER BY topic_embedding <=> query_embedding LIMIT 3`, тот же язык и ниша, cosine distance < 0.4). Найденные передаются в промпт outline_agent как примеры успешных структур (блок `$successful_examples`; если пусто — блок опускается).
- Кэш outline_agent при наличии примеров ДОЛЖЕН включать в ключ id использованных примеров (иначе рост каталога не будет влиять на закэшированные темы).

**Дальше:** после накопления 500+ статей — переход на B или D (roadmap).

---

## 19. Docker и деплой

### 19.1. Docker Compose

Приложение поставляется как `docker-compose.yml` с 4 сервисами:

```yaml
version: '3.9'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/seo
      - REDIS_URL=redis://redis:6379/0
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - XMLSTOCK_API_URL=${XMLSTOCK_API_URL}
      - PIXABAY_API_KEYS=${PIXABAY_API_KEYS}
      - UNSPLASH_ACCESS_KEYS=${UNSPLASH_ACCESS_KEYS}
      - BASIC_AUTH_USERNAME=${BASIC_AUTH_USERNAME}
      - BASIC_AUTH_PASSWORD=${BASIC_AUTH_PASSWORD}
      - WP_ENCRYPTION_KEY=${WP_ENCRYPTION_KEY}
    depends_on:
      - postgres
      - redis
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs

  worker:
    build: ./backend
    command: celery -A app.worker worker --loglevel=info --concurrency=2
    environment:
      # тот же env что и у backend
    depends_on:
      - postgres
      - redis
    volumes:
      - ./data:/app/data

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:8000
    depends_on:
      - backend

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: seo
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

  nginx:                        # опциональный: только profile 'production'
    image: nginx:1.25
    profiles: ["production"]
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
  redis_data:
```

### 19.2. Запуск

**Локально (основной режим первого релиза):**
```bash
cp env.example .env
# заполнить ключи
docker-compose up -d
# фронт: http://localhost:3000, API: http://localhost:8000
```
Nginx при локальном запуске не поднимается (profile `production`); фронт и API доступны напрямую. Basic auth остаётся включённым.

**На VPS (справочно, вне скоупа первого релиза):**
- Установить Docker + Docker Compose.
- Настроить домен → IP.
- Использовать certbot для SSL.
- Запустить `docker-compose --profile production up -d`.

### 19.3. Backups

Автоматический бэкап Postgres:
- Crontab / celery beat: `pg_dump` раз в день.
- Хранение: `data/backups/` + опционально S3.
- Retention: последние 30 дней.

Файлы (data/articles): архивирование раз в неделю.

### 19.4. Мониторинг

Минимум:
- Health check: `GET /api/health` → 200 если backend жив.
- Логи в stdout + collected via docker logging driver.

Опционально:
- Prometheus метрики (rate генераций, среднее время, ошибки).
- Grafana дашборд.

---

## 20. Промпты агентов (полные тексты как приложение)

**Внимание:** промпты — это ключевая ценность системы. Оставлены в отдельных файлах `prompts/<agent_name>/v1.txt` в архиве проекта. Разработчику **обязательно** передать эти файлы вместе с ТЗ.

### 20.1. Список промптов (файлы в `prompts/`)

- `competitor_analysis_agent/v1.txt`
- `lsi_agent/v1.txt`
- `brief_agent/v1.txt`
- `outline_agent/v1.txt`
- `writer_agent/v1.txt`
- `critic_agent/v1.txt`
- `editor_agent/v1.txt`
- `faq_writer_agent/v1.txt`
- `final_qa_agent/v1.txt`
- `metadata_agent/v1.txt`
- `archetype_picker_agent/v1.txt`
- `style_extractor_agent/v1.txt`
- `image_keys_agent/v1.txt`

**Новые промпты для реализации:**
- `sources_weaver_agent/v1.txt`
- `fact_checker_agent/v1.txt` (два — extraction + verification)

### 20.2. Работа с промптами

Каждый промпт — обычный текстовый файл с подстановкой переменных через `string.Template` (символ `$`).

Пример writer_agent v1.txt:
```
# ROLE
You are $author_name — a professional SEO editor...

Article: $article_title
Main keyword: $main_keyword
LSI keywords: $lsi_keywords
...
```

Внимание: если в тексте промпта есть символ `$` не как переменная — экранировать `$$`.

### 20.3. Версионирование промптов

- Хранить в git (репозиторий проекта).
- При изменении — создать `v2.txt`, поменять `PROMPT_VERSION = "v2"`.
- Кэш agent_cache при смене версии — инвалидировать вручную.

### 20.4. Переменные подстановки — базовый набор

Все агенты имеют доступ к:
- `$article_title`
- `$main_keyword`
- `$secondary_keywords` (comma-separated)
- `$language` (двухбуквенный код)
- `$geo`

Специфичные для агента:
- Writer: `$author_block`, `$section_spec`, `$previous_summaries`, `$lsi_keywords`, `$brief_summary`.
- Critic: `$section_text`, `$section_spec`, `$brief_summary`.
- Brief: `$competitor_analysis_json`, `$target_word_count`.
- Outline: `$brief_json`, `$competitor_analysis_json`.
- FAQ writer: `$article_summary`, `$questions`, `$brief_must_cover`.
- Sources weaver: `$article_markdown`, `$suggested_sources` (list of source objects).
- Fact checker: `$article_markdown`, `$language`.
- Metadata: `$article_markdown`, `$brief_json`, `$outline_json`.

### 20.5. Разработка новых промптов (sources_weaver, fact_checker)

Промпты `sources_weaver_agent/v1.txt` и `fact_checker_agent/v1_extraction.txt` (+ логика verification в коде) **разрабатываются исполнителем** в рамках проекта. Требования к оформлению — как у существующих промптов (см. 20.2): английский язык инструкций, `string.Template`, JSON-only ответ.

**Критерии приёмки промптов** (проверяются на 5 приёмочных статьях из Приложения D):

*sources_weaver:*
- В каждой статье 3-5 вплетённых ссылок, <= 1 на секцию, все URL отвечают 200.
- Текст вне вставленных ссылок не изменён (diff проверяется кодом).
- QA-score статьи после вплетения не снижается более чем на 2 пункта относительно прогона без weaver'а.

*fact_checker (extraction):*
- Извлекается 5-20 утверждений, каждое соответствует схеме FactStatement.
- На статьях по «энциклопедическим» темам (география, история) доля `uncertain` <= 40%.
- Ложные mismatch (проверяется вручную на выборке) <= 1 на статью.

---

## 21. Критерии приёмки

Проект считается сданным при выполнении **всех** критериев. Сдача разбита на **два этапа**; оплата/приёмка — по этапам.

**Этап 1 — ядро:**
- Пайплайн 13 шагов полностью, включая sources_weaver и fact_checker.
- UI: Главная, Написание (+ review-панель), Результат, История.
- REST + WebSocket, восстановление после перезагрузки страницы.
- Docker Compose, только русский язык.
- Приёмка: 5 приёмочных статей (ru, темы — Приложение D), avg QA >= 80; критерии 21.3 и 21.4.

**Этап 2 — полный объём:**
- Мультиязычность (6 языков, каталог референсов, pysbd, стоп-слова).
- WordPress-публикация (тестовый сайт заказчика: **russiatravelers.online**; Application Password предоставляет заказчик к началу Этапа 2).
- Аналитика, Настройки, Сайты (полные экраны).
- Самообучение — Стратегия C.
- Приёмка: smoke-test 5 языков (score >= 75), публикация черновика в тестовый WP, остальные чекбоксы раздела 21.

### 21.1. Функциональные

- [ ] Все страницы UI работают согласно спецификации (10.3-10.10).
- [ ] Все REST endpoints реализованы (11.2).
- [ ] WebSocket-события работают (11.3).
- [ ] Прогон одной статьи от старта до final_package успешно завершается на каждом из 6 языков.
- [ ] Пауза для ревью outline работает — можно продолжить и отменить.
- [ ] Публикация в WordPress работает (черновик создаётся, картинки загружаются).
- [ ] Fact-checker вызывается и передаёт отчёт в final_qa_agent.
- [ ] Sources_weaver вплетает ссылки в текст.
- [ ] Аналитика показывает основные метрики.
- [ ] Кэши работают: SERP, agent_cache, image_keys, wiki.

### 21.2. Качественные

- [ ] Средний QA-score >= 80/100 на **5 приёмочных статьях** (русский язык; темы зафиксированы в Приложении D).
- [ ] Средняя стоимость одной статьи <= $0.15.
- [ ] Среднее время генерации <= 10 минут (без пауз).
- [ ] Smoke-test мультиязычности (Этап 2): по 1 статье на каждом из остальных 5 языков (en, de, it, es, fr) → score >= 75. Темы — переводы/адаптации приёмочных.

Итого приёмочных прогонов: 10 (5 ru + 5 других языков). Прогон на 6 языках из п. 21.1 входит в эти же 10, отдельных не требуется.

### 21.3. Технические

- [ ] `docker-compose up` запускает всё окружение с одной команды.
- [ ] Все переменные окружения задокументированы в `env.example`.
- [ ] Backups Postgres работают (проверить одним прогоном dump/restore).
- [ ] Health check endpoint работает.
- [ ] Есть автотесты для критических модулей (агенты, метрики QA, кэши). Coverage >= 60%.

### 21.4. Документация

- [ ] README с инструкцией запуска.
- [ ] API документация (Swagger автоматом из FastAPI).
- [ ] Миграции Alembic применяются с нуля.
- [ ] Инструкция администратора: настройка ключей, WordPress, деплой.

### 21.5. Мультиязычность

- [ ] Все 6 языков работают в форме.
- [ ] Каталог референсов заполнен: минимум 3 автора на язык.
- [ ] QA-метрики (стоп-слова, sentence-splitter) работают для всех 6 языков.

---

## 22. Технические риски и подводные камни

Раздел о том, с чем разработчик встретится в процессе и как быть готовым.

### 22.1. LLM: галлюцинации и стабильность

**Риск:** Claude Sonnet 4.6 (как и любая LLM) может выдавать факты, которых нет в реальности. Или на два похожих запроса — разные ответы.

**Стратегия:**
- Fact-checker с обращением к внешним источникам обязателен.
- Температура низкая для structured output (critic, final_qa, extraction).
- Температура выше только для creative (writer, editor).

### 22.2. Контекст 200K токенов

**Риск:** большой SERP-бандл + brief + outline + previous_summaries могут не поместиться.

**Стратегия:**
- Никогда не передавать полные тексты конкурентов — только выжимки (h1/h2/h3 + первые 300 слов).
- Previous_summaries — только `<!-- SUMMARY: ... -->` короткие маркеры.
- Мониторить `tokens_in` в pipeline_steps.

### 22.3. Rate limits

**Риск:** Anthropic API даёт по умолчанию 40 req/min для Sonnet и 100 для Haiku. При генерации 20 статей параллельно — упрёшься.

**Стратегия:**
- Concurrent limit в Celery (`--concurrency=2`) — не запускать больше 2 пайплайнов одновременно.
- Retry с backoff при 429.

### 22.4. Wikipedia/Wikidata: русский покрытие хуже

**Риск:** Wikidata заточен под английский. Для русских тем не всегда находит.

**Стратегия:**
- Fallback: если Wikidata пусто — идти в Wikipedia через REST API.
- Для русских тем сразу приоритет — русская Wikipedia.

### 22.5. Pixabay/Unsplash: качество на русском

**Риск:** русские searchqueries дают плохие результаты.

**Стратегия:**
- image_keys_agent генерирует ключи на английском (обязательно), даже для русских статей.
- Транслит русских топонимов при поиске (Байкал → Baikal).

### 22.6. AVG длины конкурентов искажается outlier'ами

**Риск:** Википедия часто в топе с 10-20k слов — это искажает mean.

**Стратегия:** trimmed mean (без min и max) — уже в FR-14.

### 22.7. Целевая длина vs фактическая

**Риск:** LLM может систематически писать длиннее или короче требуемого.

**Стратегия:**
- Writer в промпте: "target ±15%".
- Critic снижает score при существенном отклонении.
- Length_control считать от sum(outline.sections.target_word_count).

### 22.8. Промпты — знак $

**Риск:** Python `string.Template` использует `$` для подстановки. Если в тексте промпта есть `$` не для переменной — крашит.

**Стратегия:** экранировать `$$` в текстах промптов.

### 22.9. QtWebEngine (устарел, но упомянуть)

Если разработчик решит по какой-то причине сделать десктоп-версию: file:// картинки блокируются QtWebEngine когда страница загружена с qrc://. Использовать data: URI или переключить baseUrl.

### 22.10. Кэш agent_cache и изменение Pydantic-схем

**Риск:** после изменения схемы Brief/Outline — старые кэши могут крашиться на загрузке.

**Стратегия:**
- При смене схемы — инвалидировать кэш.
- Не хранить в кэше raw_text (проще, но при parsing errors крашит).

### 22.11. Postgres JSONB и русский

**Риск:** при вставке русского текста в JSONB нужна корректная кодировка.

**Стратегия:** `client_encoding='UTF8'` в connection string.

### 22.12. WordPress: application password и категории

**Риск:** WP по умолчанию не даёт создавать категории через API без прав.

**Стратегия:**
- Application Password должен быть с админ-правами.
- Если категория не найдена — попытаться создать `POST /wp-json/wp/v2/categories`. При ошибке — использовать "Без категории" (id=1).

### 22.13. Fact-checker: false positives

**Риск:** Wikidata может иметь неточные факты (10% ошибок). Наш "mismatch" может быть ошибочным.

**Стратегия:**
- Statuses: verified / mismatch / uncertain — использовать uncertain при низкой confidence.
- Пороги: строго снижать factuality только при >20% mismatches.
- Не автоматически исправлять статью.

### 22.14. WebSocket-соединения

**Риск:** при потере соединения — клиент не видит завершение.

**Стратегия:**
- Redis pub/sub с TTL сообщений.
- REST endpoint `GET /api/pipeline/{id}/status` — можно получить актуальный статус в любой момент.
- Клиент при reconnect — сначала GET, потом WebSocket.

### 22.15. Deploy: смена секретов

**Риск:** смена инфраструктурных секретов (`DATABASE_URL`, ключи шифрования, basic auth) требует перезапуска контейнеров.

**Стратегия:**
- API-ключи внешних сервисов хранятся в БД (таблица `app_settings`, см. 10.10) и меняются через UI без рестарта.
- Инфраструктурные секреты — в .env файле (не в docker-compose).
- Для production — использовать Docker secrets.

---

## 23. Out of scope — что НЕ входит в задачу

Разработчик **не должен** пытаться реализовать следующее (защита от расширения скоупа):

- **Мобильные нативные приложения** (iOS/Android SDK) — только адаптивная веб-версия.
- **Мультитенантность** — одна инсталляция обслуживает одну команду / одного пользователя. Разделение по клиентам не предусмотрено.
- **Биллинг / тарифы / платежи** — приложение без коммерческой модели.
- **i18n интерфейса** — интерфейс только на русском. Статьи — на 6 языках.
- **Дообучение LLM (fine-tuning)** — Anthropic не даёт публичный API для этого. Использовать только public API.
- **Полностью автоматический fact-checking через все источники интернета** — только Wikipedia REST API + Wikidata SPARQL. Другие БД (например, Britannica API, Google Custom Search) — не включены.
- **Редактирование готовой статьи в UI** — после генерации статья read-only. Правки — вручную через `.md` файл или в WordPress admin.
- **Совместное редактирование в реальном времени** — приложение однопользовательское.
- **Аналитика внешнего трафика** (Google Search Console API, Yandex Wordstat) — только внутренняя статистика по генерации.
- **A/B-тесты промптов** — можно оставить в roadmap. Первый релиз использует единую версию v1.
- **Уведомления пользователю (email, telegram)** — только in-app уведомления.
- **Восстановление незавершённой генерации** после падения worker'а — при рестарте задача помечается failed. Пользователь запускает заново (кэши агентов помогут).
- **Экспорт в форматах отличных от markdown+html** — не поддерживать PDF, DOCX и т.п.
- **Автоматический выбор архетипа без ручного подтверждения** — всегда предлагать пользователю подтвердить.
- **Автоматическое перепубликование** статей — только вручную "Опубликовать в WordPress".
- **Множественные account'ы WordPress** на один сайт — один WP account на сайт.
- **Учёт региональности контента** отдельно от языка — geo используется как справочная информация.
- **Автоматический подбор картинок через AI-генерацию (DALL-E, Midjourney)** — только стоки (Pixabay/Unsplash/Wikimedia).

---

**Конец документа.**

---

## Приложение A. Термины и сокращения

- **SERP** — Search Engine Results Page. Топ-10 результатов поиска Google.
- **LSI** — Latent Semantic Indexing. Тематически связанные слова.
- **EEAT** — Experience, Expertise, Authoritativeness, Trustworthiness. Google-концепция качества.
- **QA** — Quality Assurance. Контроль качества статьи.
- **RAG** — Retrieval-Augmented Generation. Генерация с обращением к внешнему индексу.
- **SPARQL** — SPARQL Protocol and RDF Query Language. Запросы к Wikidata.
- **JSON-LD** — JSON for Linking Data. Формат Schema.org разметки.
- **Application Password** — специальный WP пароль для API-доступа.

## Приложение B. Ссылки на документацию

- Anthropic API: https://docs.anthropic.com/
- Pixabay API: https://pixabay.com/api/docs/
- Unsplash API: https://unsplash.com/documentation
- Wikimedia Commons API: https://commons.wikimedia.org/wiki/Commons:API
- Wikipedia REST API: https://en.wikipedia.org/api/rest_v1/
- Wikidata SPARQL: https://query.wikidata.org/
- WordPress REST API: https://developer.wordpress.org/rest-api/
- FastAPI: https://fastapi.tiangolo.com/
- Celery: https://docs.celeryq.dev/
- Pydantic: https://docs.pydantic.dev/
- pgvector: https://github.com/pgvector/pgvector
- pysbd (sentence boundary): https://github.com/nipunsadvilkar/pySBD
- stopwordsiso: https://github.com/stopwords-iso/stopwords-iso

## Приложение D. Приёмочные темы (5 статей, русский язык)

Темы для приёмки Этапа 1 (критерий 21.2: средний QA-score >= 80). Все — географические/энциклопедические с хорошим покрытием в русской Wikipedia (важно для корректной работы fact-checker: минимум `uncertain`-утверждений). Подобраны разные архетипы для проверки пайплайна на разной структуре.

| # | article_title | main_keyword | secondary_keywords | Ожидаемый архетип |
|---|---|---|---|---|
| 1 | Эльбрус: где находится, высота и интересные факты | эльбрус где находится | высота эльбруса, эльбрус на карте, восхождение на эльбрус | travel-destination-guide / facts |
| 2 | Долина гейзеров на Камчатке: как добраться, когда ехать и что посмотреть | долина гейзеров камчатка | долина гейзеров как добраться, гейзеры камчатки, кроноцкий заповедник | travel-destination-guide |
| 3 | Куршская коса: национальный парк, достопримечательности и маршруты | куршская коса | куршская коса достопримечательности, танцующий лес, куршская коса как добраться | travel-top-list |
| 4 | Ленские столбы в Якутии: где находятся, высота и как добраться | ленские столбы | ленские столбы якутия, ленские столбы как добраться, природный парк ленские столбы | travel-destination-guide / facts |
| 5 | Озеро Селигер: где находится, глубина и отдых на озере | озеро селигер | селигер где находится, глубина селигера, отдых на селигере, нилова пустынь | travel-destination-guide / facts |

**Параметры прогона для всех пяти:** `language=ru`, `geo=ru`, `length_strategy=match_top`, `required_elements=[faq, quick_answer, table, weaved_sources]`, `review_outline=true` (подтверждение структуры без правок — если правки нужны, это фиксируется в отчёте о приёмке), `enable_section_critic=true`.

Тема №5 (Селигер) структурно близка к эталонной статье про Байкал из пакета передачи (`reference_article/`) — использовать её для прямого сравнения качества с desktop-версией.

Эти же 5 статей используются для приёмки промптов sources_weaver и fact_checker (п. 20.5). Для smoke-теста Этапа 2 (п. 21.2) темы №1-5 адаптируются/переводятся на en, de, it, es, fr — по одной на язык.

## Приложение C. Статусы статьи (articles.status)

`created` → `input_validated` → `serp_done` → `competitor_analysis_done` → `brief_done` → `outline_done` → `sections_in_progress` → `draft_ready` → `images_done` → `sources_done` → `fact_check_done` → `qa_done` → терминальные: `completed` | `ready_for_manual_review` | `ready_for_manual_review_with_warnings` | `failed` | `stopped_by_user` | `review_timeout`.

