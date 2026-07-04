# SEO Pipeline — Архитектурная документация

**Версия документа:** 1.0
**Дата:** 3 июля 2026
**Статус:** Актуальное описание системы на текущий момент
**Аудитория:** разработчик, который будет проверять корректность ТЗ и (возможно) реализовывать альтернативную версию

---

## Содержание

1. [Цель приложения и позиционирование](#1-цель-приложения-и-позиционирование)
2. [Стек и окружение](#2-стек-и-окружение)
3. [Структура проекта](#3-структура-проекта)
4. [Модель данных (PostgreSQL)](#4-модель-данных-postgresql)
5. [Файловое хранилище](#5-файловое-хранилище)
6. [Схемы данных (Pydantic)](#6-схемы-данных-pydantic)
7. [Пайплайн генерации статьи (11 шагов)](#7-пайплайн-генерации-статьи-11-шагов)
8. [Агенты — детальное описание каждого](#8-агенты-—-детальное-описание-каждого)
9. [Сервисы (общая функциональность)](#9-сервисы-общая-функциональность)
10. [Кэширование](#10-кэширование)
11. [UI-архитектура](#11-ui-архитектура)
12. [Внешние интеграции](#12-внешние-интеграции)
13. [Конфигурация и переменные окружения](#13-конфигурация-и-переменные-окружения)
14. [Логирование и отладка](#14-логирование-и-отладка)
15. [Известные ограничения и особенности](#15-известные-ограничения-и-особенности)

---

## 1. Цель приложения и позиционирование

**SEO Pipeline** — это генератор SEO-статей для контент-сайтов на основе LLM-агентов Anthropic (Claude Sonnet 4.6 и Haiku 4.5). Работает как настольное приложение на PySide6 с интерфейсом, встроенным в QtWebEngine (HTML/CSS/JS внутри Qt-окна).

### Задача
Заменить ручную работу копирайтера SEO-статей автоматизированным пайплайном: от анализа топ-10 поисковой выдачи до готового markdown-документа с картинками, метаданными и внутренней разметкой.

### Ключевые пользовательские преимущества
- **Многоагентная генерация** — каждый шаг делает специализированный агент (анализ конкурентов, brief, outline, писатель, критик, редактор, QA).
- **Автоматизация полного цикла** — от ввода темы до готовой публикации с картинками и метаданными.
- **QA-контроль качества** — гибридная оценка: детерминированные метрики (кодом) + LLM-критик по 9 критериям.
- **Управление стилем** — привязка к автору-референсу (реальному писателю), стиль извлекается один раз и переиспользуется.
- **Пауза для ревью** — после генерации outline пользователь может отредактировать структуру перед генерацией текста.
- **Работа с несколькими сайтами** — каждый сайт со своей нишей, авторами, стилями, статистикой.

### Целевая аудитория
- SEO-специалисты и контент-менеджеры, которые ведут несколько сайтов.
- Владельцы контент-проектов (агрегаторы, блоги, справочные сайты).
- Индивидуальные авторы, работающие над несколькими нишами.

---

## 2. Стек и окружение

### Основной стек

| Компонент | Технология | Версия | Роль |
|---|---|---|---|
| Runtime | Python | 3.12+ | Основной язык |
| GUI | PySide6 (Qt 6.7+) | >=6.7.0 | Оконная система |
| WebView | QtWebEngine | входит в PySide6 | Рендер HTML/CSS/JS UI |
| БД | PostgreSQL | 13+ | Метаданные, справочники, статистика |
| БД-драйвер | psycopg2-binary | >=2.9.9 | Пул соединений |
| ORM/схемы | Pydantic | >=2.7.0 | Валидация и сериализация |
| LLM | Anthropic Claude API | Sonnet 4.6 / Haiku 4.5 | Генерация текста |
| SERP | XMLStock (self-hosted парсер) | REST | Поиск в топ-10 Google |
| Картинки | Pixabay + Unsplash + Wikimedia | REST API | Стоковые фотографии |
| Обработка картинок | Pillow | latest | Resize, crop, WebP |
| Веб-парсинг | BeautifulSoup4 + lxml + readability-lxml | actual | Извлечение текста конкурентов |
| Аналитика | pandas, numpy, scikit-learn | actual | Метрики, тренды |

### Полный список зависимостей (`requirements.txt`)

```
# LLM
openai>=1.40.0
anthropic>=0.34.0
google-generativeai>=0.8.0

# GUI
PySide6>=6.7.0

# Data / validation
pydantic>=2.7.0
python-dotenv>=1.0.0

# SERP / web
requests>=2.32.0
beautifulsoup4>=4.12.0
lxml>=5.2.0
readability-lxml>=0.8.1
tldextract>=5.1.2
stopwordsiso>=0.6.1

# Data analysis
pandas>=2.2.0
numpy>=1.26.0
scikit-learn>=1.5.0

# Database
psycopg2-binary>=2.9.9

# Utils
uuid6>=2024.1.12
```

### Точка входа

Приложение запускается через `run.py`:
```python
from app.main import main
if __name__ == "__main__":
    main()
```

`app/main.py` инициализирует БД, создаёт QApplication, стартует MainWindow.

---

## 3. Структура проекта

Дерево на верхнем уровне:

```
seo_pipeline/
├── app/                          # исходный код приложения
│   ├── __init__.py
│   ├── main.py                   # точка входа: init_db + запуск GUI
│   ├── agents/                   # 13 агентов LLM (один агент = один класс)
│   ├── config/                   # настройки: пути, модели, версии
│   ├── llm/                      # клиент к LLM-провайдеру (Anthropic)
│   ├── orchestrator/             # оркестратор пайплайна + section_pipeline + status_manager
│   ├── prompts/                  # loader для .txt файлов промптов
│   ├── schemas/                  # Pydantic-модели данных
│   ├── services/                 # утилитарные сервисы (кэш, парсеры, метрики)
│   │   └── image_finder/         # провайдеры картинок (pixabay, unsplash, wikimedia)
│   ├── storage/                  # БД, файловое хранилище, репозитории
│   ├── ui/                       # main_window.py — всё UI на HTML/CSS/JS + Qt
│   └── utils/                    # id-генерация, time, text helpers
├── prompts/                      # .txt файлы промптов агентов (по одной папке на агент)
├── data/                         # runtime data
│   ├── articles/                 # <slug>_<id>/ — папки конкретных статей
│   ├── serp_cache/               # кэш SERP-запросов
│   ├── agent_cache/              # кэш вызовов агентов
│   ├── image_keys_cache.json     # кэш ключей для поиска картинок
│   ├── translation_cache.json    # кэш переводов
│   └── style_references/         # extracted styles писателей-референсов
├── logs/                         # runtime logs
├── requirements.txt
├── env.example                   # шаблон для .env
├── run.py                        # entry point
├── BACKLOG.md                    # список задач и планов
└── README.md
```

### Ключевые файлы по размеру

| Файл | Строк | Что это |
|---|---|---|
| `app/ui/main_window.py` | ~3185 | Весь UI: HTML/CSS/JS + Qt Bridge |
| `app/orchestrator/pipeline_orchestrator.py` | ~692 | Оркестратор пайплайна, 11 шагов |
| `app/storage/db_manager.py` | ~424 | Схема БД + seed данные |
| `app/storage/repositories.py` | ~446 | Запросы к БД |
| `app/orchestrator/section_pipeline.py` | ~204 | Пайплайн одной секции (Writer→Critic→Editor) |
| `app/agents/*.py` | 60–200 | Каждый агент отдельно |

---

## 4. Модель данных (PostgreSQL)

Схема создаётся автоматически при первом запуске (`init_db()` в `db_manager.py`).

### Таблицы

#### 1. `niches` — справочник ниш сайтов

```sql
CREATE TABLE niches (
    niche_id     TEXT PRIMARY KEY,           -- 'travel', 'home', 'auto', ...
    name_ru      TEXT NOT NULL,               -- 'Трэвел / путешествия'
    description  TEXT                         -- краткое описание
);
```

Seed при инициализации: `travel`, `home`, `auto`, `lifestyle`, `pets`, `garden`, `utility`.

#### 2. `archetypes` — типы статей по нишам

```sql
CREATE TABLE archetypes (
    archetype_id     TEXT PRIMARY KEY,        -- 'travel-destination-guide'
    niche_id         TEXT REFERENCES niches(niche_id),
    name_ru          TEXT NOT NULL,           -- 'Путеводитель по направлению'
    description      TEXT,                    -- 'Как добраться, когда ехать...'
    intent_triggers  TEXT[]                   -- ['informational', 'how_to']
);
```

Seed при инициализации: 30+ архетипов по всем 7 нишам. Пример travel-архетипов: `travel-destination-guide`, `travel-route`, `travel-top-list`, `travel-comparison`, `travel-personal`, `travel-practical-guide`.

#### 3. `sites` — сайты пользователя

```sql
CREATE TABLE sites (
    domain      TEXT PRIMARY KEY,             -- 'kroppa.ru'
    name        TEXT NOT NULL,                -- 'Kroppa Travel'
    niche_id    TEXT REFERENCES niches(niche_id),
    is_test     BOOLEAN NOT NULL DEFAULT FALSE,   -- отделяет тестовые статьи
    created_at  TEXT NOT NULL
);
```

По умолчанию создаётся тестовый сайт `example.net` (is_test=TRUE) — на него привязываются все прогоны без явно выбранного сайта.

#### 4. `style_references` — писатели-референсы

```sql
CREATE TABLE style_references (
    reference_id          TEXT PRIMARY KEY,   -- 'dovlatov', 'ulitskaya', ...
    name                  TEXT NOT NULL,      -- 'Сергей Довлатов'
    language              TEXT NOT NULL,      -- 'ru'
    geo                   TEXT NOT NULL,      -- 'ru' | 'de' | 'it' ...
    niche_tags            TEXT[],             -- ['travel', 'lifestyle']
    notes                 TEXT,               -- заметки об использовании
    extracted_style       TEXT,               -- style_extractor_agent результат
    extracted_tone        TEXT,
    extracted_age_image   TEXT,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TEXT NOT NULL
);
```

#### 5. `authors` — авторы сайтов (виртуальные)

```sql
CREATE TABLE authors (
    author_id    TEXT PRIMARY KEY,
    site_domain  TEXT REFERENCES sites(domain),
    name         TEXT NOT NULL,               -- 'Михаил Окольн'
    character    TEXT,                        -- character description
    tone         TEXT,                        -- 'ironic, melancholic, dry'
    age_image    TEXT,                        -- '40-50 лет, ...'
    niche_id     TEXT REFERENCES niches(niche_id),
    reference_id TEXT REFERENCES style_references(reference_id),  -- FK на референс
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TEXT NOT NULL
);
```

Автор берётся Writer'ом при генерации: `character` + `tone` + `age_image` подставляются в промпт как «АВТОР СТАТЬИ».

#### 6. `articles` — статьи

```sql
CREATE TABLE articles (
    article_id    TEXT PRIMARY KEY,           -- UUID
    site_domain   TEXT REFERENCES sites(domain),
    author_id     TEXT REFERENCES authors(author_id),
    archetype_id  TEXT REFERENCES archetypes(archetype_id),
    title         TEXT,
    main_keyword  TEXT,
    status        TEXT,                       -- см. STATUS_* константы
    qa_status     TEXT,                       -- 'ready_for_manual_review' | 'failed' | ...
    qa_score      INTEGER,                    -- 0-100
    cost_usd      NUMERIC(10,6) DEFAULT 0,    -- суммарная стоимость LLM-вызовов
    created_at    TEXT,
    updated_at    TEXT
);
```

Статусы (`app/config/pipeline_settings.py`):
`created` → `input_validated` → `serp_done` → `competitor_analysis_done` → `brief_done` → `outline_done` → `sections_in_progress` → `draft_ready` → `qa_done` → `ready_for_manual_review[/_with_warnings]` → `completed` / `failed` / `stopped_by_user`.

#### 7. `pipeline_steps` — журнал шагов

```sql
CREATE TABLE pipeline_steps (
    id            SERIAL PRIMARY KEY,
    article_id    TEXT,
    step_name     TEXT,                       -- 'serp_analysis', 'brief_generation', ...
    status        TEXT,                       -- 'running' | 'done' | 'failed'
    started_at    TEXT,
    finished_at   TEXT,
    error_message TEXT
);
```

Отслеживает каждый шаг пайплайна: старт, конец, ошибку.

#### 8. `sections` — секции статьи (для мониторинга)

```sql
CREATE TABLE sections (
    id          SERIAL PRIMARY KEY,
    article_id  TEXT,
    section_id  TEXT,                         -- 's0', 's1_1', 'faq_auto', ...
    status      TEXT,                         -- 'pending' | 'running' | 'done' | 'failed'
    iterations  INTEGER DEFAULT 0,            -- сколько раз Writer перегенерировал (по требованию Critic)
    word_count  INTEGER DEFAULT 0
);
```

Используется UI для показа прогресса по секциям во время генерации.

#### 9. `archetype_picks` — статистика подбора архетипов

```sql
CREATE TABLE archetype_picks (
    id                      SERIAL PRIMARY KEY,
    article_id              TEXT REFERENCES articles(article_id),
    suggested_archetype_id  TEXT REFERENCES archetypes(archetype_id),
    chosen_archetype_id     TEXT REFERENCES archetypes(archetype_id),
    matched                 BOOLEAN NOT NULL,   -- true если юзер подтвердил suggested
    niche_id                TEXT REFERENCES niches(niche_id),
    intent                  TEXT,
    created_at              TEXT NOT NULL
);
```

Для аналитики: как часто предложенный архетип совпадает с выбранным.

### Индексы

Явно в коде не создаются — Postgres авто-создаёт индексы только для PRIMARY KEY. Для быстрой аналитики полезно добавить (в бэклоге):
- `CREATE INDEX ON articles(site_domain, created_at DESC)`
- `CREATE INDEX ON pipeline_steps(article_id)`
- `CREATE INDEX ON sections(article_id)`

---

## 5. Файловое хранилище

Каждая статья получает свою папку в `data/articles/<slug>_<uuid_short>/`.

Пример: `data/articles/ozero-bajkal-gde-nakhoditsya-glubina-koordinaty-i-_d4c640e7/`

### Что внутри

```
ozero-bajkal-gde-...._d4c640e7/
├── article_input.json               # ArticleInput.to_dict()
├── serp_bundle.json                 # ответ от XMLStock (топ-10 и распарсенный контент)
├── competitor_analysis_report.json  # результат competitor_analysis_agent
├── brief.json                       # результат brief_agent
├── outline.json                     # результат outline_agent
├── full_draft.json                  # FullDraft после assemble_draft
├── article.md                       # финальный markdown статьи
├── qa_result.json                   # результат final_qa_agent
├── final_package.json               # FinalPackage (meta_title, meta_description, tags и т.д.)
├── images/                          # локальные картинки статьи
│   ├── 1.webp                       # 1280x720, WebP quality=70
│   ├── 2.webp
│   └── 3.webp
├── sections/                        # результаты каждой секции по итерациям
│   ├── s0_writer_1.json
│   ├── s0_critic_1.json
│   ├── s0_writer_2.json             # (если Critic попросил переписать)
│   └── s0_final.json
└── prompts/                         # промпты и ответы всех вызовов LLM
    ├── serp_analysis_prompt.txt
    ├── serp_analysis_response.txt
    ├── competitor_analysis_prompt.txt
    ├── competitor_analysis_response.txt
    ├── brief_generation_prompt.txt
    ├── ...
    └── section_s0_writer_1_prompt.txt
```

### Именование папок (`slugify`)

Функция `slugify()` в `utils/text_utils.py`:
1. Транслитерация кириллицы в латиницу.
2. Замена пробелов на дефисы.
3. Обрезка до 50 символов.
4. Суффикс: `_<short_uuid>` — первые 8 символов UUID.

### Кэши в data/

- `data/serp_cache/<hash>.json` — по хэшу от `(main_keyword, geo, language)`.
- `data/agent_cache/<agent_name>/<hash>.json` — по хэшу от контекста вызова агента.
- `data/image_keys_cache.json` — по `main_keyword`.
- `data/translation_cache.json` — по хэшу от исходной строки + языковой пары.

---

## 6. Схемы данных (Pydantic)

Все схемы данных — Pydantic BaseModel, живут в `app/schemas/`.

### `ArticleInput` (`article_input.py`)

Ключевые поля:

| Поле | Тип | Обязательное | Примечание |
|---|---|---|---|
| `article_id` | str (UUID) | auto | Основной идентификатор |
| `article_title` | str | ✓ | 5–300 символов |
| `main_keyword` | str | ✓ | 2–300 символов |
| `secondary_keywords` | List[str] | ✓ | ≥1 элемент |
| `length_strategy` | str | default | `shorter_top`/`match_top`/`longer_top`/`custom` |
| `target_word_count` | Optional[int] | если custom | 300–10000 |
| `language` | str | ✓ | двухбуквенный код (ru, en, de, ...) |
| `geo` | str | ✓ | код страны |
| `intent` | str | ✓ | `informational` \| `how_to` |
| `article_type` | str | ✓ | `informational` \| `how_to` |
| `difficulty` | str | ✓ | `easy` \| `medium` \| `hard` |
| `style_archetype` | str | ✓ | `expert_clear`/`friendly_practical`/`calm_analytical`/`editorial_neutral` |
| `required_elements` | List[str] | ✓ | подмножество: `faq`, `quick_answer`, `table`, `list`, `conclusion`, `sources_block` |
| `site_domain` | str | default | `example.net` |
| `author_id` | Optional[str] | нет | FK на author |
| `always_review_sections` | bool | default True | триггер паузы для ручного ревью |
| `force_refresh_serp` | bool | default False | игнорировать SERP-кэш |
| `serp_json_path` | Optional[str] | нет | путь к готовому SERP JSON |
| `manual_sources` | Optional[List[str]] | нет | ручные URLs вместо SERP |

### `CompetitorAnalysisReport` (`competitor_analysis_report.py`)

```python
class WordCountRange(BaseModel):
    min: int = 0
    avg: float = 0.0
    max: int = 0
    per_page: List[int] = []

class CompetitorAnalysisReport(BaseModel):
    search_intent:      str = "informational"
    content_type:       str = "guide"
    content_format:     str = "long_read"
    word_count_range:   WordCountRange
    h2_count_range:     H2CountRange
    common_h2_titles:   List[CommonH2Title]
    structure_patterns: List[str]
    common_sections:    List[str]
    must_have_topics:   List[str]
    optional_topics:    List[str]
    content_gaps:       List[ContentGap]     # точки роста
    tone:               str = "neutral_informational"
    target_audience:    str = ""
    data_sensitivity:   DataSensitivity
    raw_report:         str = ""
```

### `Brief` (`brief.py`)

```python
class Brief(BaseModel):
    goal:               str = ""
    search_intent:      str = "informational"
    target_audience:    str = ""
    content_archetype:  str = "guide"
    tone:               str = "neutral_informational"
    style_requirements: List[str] = []
    must_cover:         List[str] = []
    must_not_cover:     List[str] = []
    structure_guidelines: List[str] = []
    word_count_target:  int = 1200
    word_count_range:   WordCountRange
    keywords:           KeywordsBlock       # main + secondary
    lsi_keywords:       List[str] = []      # тематический словарь
    required_elements:  List[str] = []
    forbidden_words:    List[str] = []
    data_handling_rules: DataHandlingRules
    raw_brief:          str = ""
```

### `Outline` (`outline.py`)

```python
class SectionSpec(BaseModel):
    section_id:       str
    title:            str
    level:            str = "H2"          # H2 | H3
    purpose:          str = ""
    target_word_count: int = 200
    keywords:         List[str] = []
    must_cover:       List[str] = []

class FaqSection(BaseModel):
    enabled:   bool = False
    questions: List[str] = []

class Outline(BaseModel):
    h1:          str = ""
    sections:    List[SectionSpec]
    faq_section: FaqSection
```

### `FullDraft` (`output_schemas.py`)

```python
class SectionFinal(BaseModel):
    section_id: str
    title:      str = ""
    content:    str = ""

class FullDraft(BaseModel):
    h1:               str = ""
    content_markdown: str = ""
    sections:         List[SectionFinal]
    word_count:       int = 0
    section_count:    int = 0
```

### `QAResult` (`output_schemas.py`)

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

class QAResult(BaseModel):
    status:          str    # 'pass' | 'pass_with_warnings' | 'fail'
    score:           int    # 0-100
    criteria_scores: CriteriaScores
    warnings:        List[str]
    fail_reasons:    List[str]
    recommendation:  str
```

### `FinalPackage` (`output_schemas.py`)

```python
class FinalPackage(BaseModel):
    article_id:       str
    slug:             str
    meta_title:       str
    meta_description: str
    article_markdown: str
    faq:              List[FaqItem]
    schema_data:      SchemaBlock       # JSON-LD FAQPage
    category:         str
    tags:             List[str]
    internal_links_suggestions: List[str]
```

### `SerpBundle` (`serp_bundle.py`)

Обёртка над ответом XMLStock: топ-10 URLs, каждый с распарсенным текстом и метаданными.

### `SectionAttempt`, `CriticFeedback` (`section_schemas.py`)

Для мониторинга итераций Writer→Critic→Editor.

---

## 7. Пайплайн генерации статьи (11 шагов)

Оркестратор — `app/orchestrator/pipeline_orchestrator.py` (класс `PipelineOrchestrator`). Метод `_execute()` содержит основной flow. Работает в отдельном QThread, чтобы не блокировать UI.

### Общая последовательность

| # | Шаг | Агент | Модель | На входе | На выходе |
|---|---|---|---|---|---|
| 1 | SERP-анализ | — | — | `main_keyword` | `serp_bundle.json` |
| 2 | Анализ конкурентов | `competitor_analysis_agent` | Sonnet | `serp_bundle`, `article_input` | `CompetitorAnalysisReport` |
| 3 | LSI-ключи | `lsi_agent` | Haiku | `competitor_report` | `List[str]` — 15–20 LSI-слов |
| 4 | Формирование ТЗ (Brief) | `brief_agent` | Sonnet | `competitor_report`, `lsi_keywords`, `article_input` | `Brief` |
| 5 | Outline (структура) | `outline_agent` | Sonnet | `brief`, `competitor_report` | `Outline` |
|   | **Пауза для ревью** | — | — | `Outline`, `Archetype-suggestion` | подтверждённый `Outline` |
| 6 | Секции (для каждой s0...sN) | `writer_agent` → `critic_agent` → `editor_agent` | Sonnet | `SectionSpec` из outline | `SectionFinal` |
| 7 | Сборка markdown | `markdown_builder.assemble_draft` | — | `Outline`, финальные секции | `FullDraft` |
| 8 | Поиск и вставка картинок | `image_finder_agent` | Haiku (для ключей) | `article.md`, `main_keyword` | markdown с картинками + `images/*.webp` |
| 9 | FAQ (если нет в outline) | `faq_writer_agent` | Sonnet | `outline.faq_section.questions`, статья | markdown-блок FAQ |
| 10 | Финальный QA | `final_qa_agent` | Sonnet + код | `FullDraft`, `Brief`, `CompetitorReport` | `QAResult` |
| 11 | Метаданные | `metadata_agent` | Sonnet | `FullDraft`, `Brief`, `Outline` | `FinalPackage` |

### Детальный поток

1. **Шаг 1 — SERP-анализ**
   - `serp_loader.load_from_cache(main_keyword, geo, language)` — если кэш есть, берём его.
   - Если нет — HTTP GET на XMLStock, парсинг ответа, извлечение текста каждой страницы (`readability-lxml` для main content).
   - Сохраняется как `serp_bundle.json` в папке статьи.
2. **Шаг 2 — Анализ конкурентов**
   - `competitor_analysis_agent.run(article_input, serp_bundle)`.
   - На выходе `CompetitorAnalysisReport`: диапазоны длины, частые H2, must-have topics, content gaps, тон.
3. **Шаг 3 — LSI-ключи**
   - `lsi_agent.run(article_input, competitor_report)`.
   - Промпту передаётся выжимка SERP (топ-заголовки, must-have, content gaps).
   - На выходе 15–25 английских ключей (для последующего поиска картинок).
4. **Шаг 4 — Формирование ТЗ (Brief)**
   - `brief_agent.run(article_input, competitor_report)`.
   - Внутри: `_compute_target_word_count()` — считает целевую длину исходя из стратегии (shorter/match/longer × avg конкурентов) или берёт кастомную.
   - На выходе `Brief`.
5. **Шаг 5 — Outline**
   - `outline_agent.run(article_input, brief, competitor_report)`.
   - На выходе `Outline` с секциями и опциональным `faq_section`.
6. **Пауза для ревью (условно)**
   - Если `article_input.always_review_sections=True` — оркестратор публикует специальное сообщение в лог `__REVIEW_READY__:{...}` и уходит в `_pause_event.wait()`.
   - UI показывает review-панель: сжатую сводку конкурентов, точки роста, редактируемый outline.
   - Пользователь редактирует и жмёт «Продолжить» → `resume_with_outline(outline_data)` → пайплайн получает новый outline.
7. **Шаг 6 — Секции**
   - Для каждой `SectionSpec`: `run_section()` из `section_pipeline.py`:
     1. Writer генерирует текст секции (учитывая автора, контекст предыдущих секций, LSI, must_cover).
     2. Если `always_review_sections=True` — Critic оценивает секцию (0–100 по 6 критериям).
     3. Если оценка < порога — Editor редактирует, снова Critic.
     4. Максимум `SECTION_MAX_ITERATIONS` итераций (по умолчанию 3).
   - Каждая секция сохраняется как `sections/s{id}_writer_N.json` и `sections/s{id}_final.json`.
8. **Шаг 7 — Сборка**
   - `assemble_draft(outline, final_sections)` → `FullDraft`.
   - Пишется `article.md`.
9. **Шаг 8 — Картинки**
   - `image_finder_agent.run(...)`.
   - Находит точки вставки: плейсхолдеры (`<!-- IMAGE -->`) + автоматически после H2/H3.
   - Генерирует 10 английских ключей поиска через Haiku (кэшируется по `main_keyword`).
   - По очереди для каждой точки: Pixabay → Unsplash → Wikimedia. Дедупликация по URL.
   - Скачивает, обрезает 16:9, конвертирует в WebP quality=70, сохраняет в `images/N.webp`.
   - Вставляет относительные пути в markdown с подписью источника.
10. **Шаг 9 — FAQ**
    - Если в outline.sections уже есть секция с "faq" в id или title — пропускаем.
    - Иначе `faq_writer_agent.run_with_questions(article_input, brief, article_markdown, questions, author)`.
    - Генерирует ответы 40–60 слов на каждый вопрос из `outline.faq_section.questions` (стиль автора, snippet-format).
    - Вставляется перед секцией "Заключение".
11. **Шаг 10 — Финальный QA**
    - Сначала `qa_metrics.calc_code_metrics()` — детерминированные метрики без LLM:
      - `length_control` — отклонение от `brief.word_count_target`.
      - `completeness` — присутствие `required_elements`.
      - `keyword_usage` — плотность main + покрытие secondary.
      - `structure` — наличие H1, H2, H3, введения.
      - `readability` — доля длинных предложений.
      - `lsi_coverage` — покрытие LSI-слов.
    - Затем `final_qa_agent.run(...)` — LLM оценивает 3 субъективных критерия (brief_alignment, intent_coverage, factuality) с калибровкой шкалы: 70–85 нормальное состояние, ниже 50 непригодно.
    - Итог: `QAResult` с общим score (взвешенное среднее) и статусом.
12. **Шаг 11 — Метаданные**
    - `metadata_agent.run(article_input, brief, outline, full_draft)`.
    - На выходе `FinalPackage`: slug, meta_title, meta_description, теги, категория, JSON-LD FAQPage, `internal_links_suggestions`.

### Пауза и остановка

- `stop_flag` (Event) — проверяется в `_check_stop()` перед каждым шагом. Если set — RaiseException, статья помечается `stopped_by_user`.
- `pause_event` — используется только для ревью outline. `_pause_event.wait()` блокирует поток до `resume_with_outline()`.

### Кэширование внутри пайплайна

Три из шагов кэшируются через `agent_cache`:
- `competitor_analysis_agent`
- `lsi_agent`
- `brief_agent`
- `outline_agent`

Ключ кэша: `agent_name + article_title + main_keyword + sorted(secondary_keywords)`. Не участвуют: language, geo, intent (всегда жёстко связаны с темой).

Если пользователь редактирует outline и жмёт «Продолжить» — кэш outline **не пересобирается** (используется отредактированная версия).

---

*Продолжение в части 2...*

---

## 8. Агенты — детальное описание каждого

Все агенты наследуются от `BaseAgent` (`app/agents/base_agent.py`). BaseAgent предоставляет:
- Загрузку промпта из `prompts/<agent_name>/v1.txt` через `prompt_loader`.
- Обёртку `_call(variables)` — подставляет переменные, зовёт LLM, ретраит при ошибках через `retry_service`.
- Обёртку `_parse_json(text)` — снимает `​`​`​`json обёртки, парсит.
- `set_stop_flag()` — прерывает ретраи если пользователь нажал Stop.
- Атрибуты `last_prompt`, `last_response`, `last_tokens_in`, `last_tokens_out` — для сохранения в prompts/ и подсчёта cost.

Модели: см. `app/config/llm_settings.py`. Основная — Claude Sonnet 4.6 (`claude-sonnet-4-6`). Haiku 4.5 (`claude-haiku-4-5-20251001`) для дешёвых коротких задач.

### 8.1. `competitor_analysis_agent` (Sonnet)

**Задача:** проанализировать топ-10 из SERP и вернуть структурированный отчёт: диапазон длины конкурентов, общие H2, must-have темы, content gaps (точки роста), тон, аудитория.

**Ключевые входы:**
- `article_input` — тема, интент, тип.
- `serp_bundle` — топ-10 URL с распарсенным содержимым.

**Ключевой выход:** `CompetitorAnalysisReport`.

**Промпт:** `prompts/competitor_analysis_agent/v1.txt` (передаётся сжатое представление конкурентов, чтобы не переполнять контекст).

**Особенности:**
- Работает по всему SERP-бандлу — но передаёт LLM только h1/h2/h3-структуру каждой страницы + первые 300 слов, чтобы уложиться в контекст.
- Считает `word_count_range.avg` как обычное среднее (в бэклоге — переход на медиану/trimmed mean).

### 8.2. `lsi_agent` (Haiku)

**Задача:** извлечь 15–20 LSI-слов (тематически связанных, но не совпадающих с main/secondary keywords) на основе SERP-выжимки.

**Входы:**
- `article_input`
- `competitor_report.common_h2_titles`, `content_gaps`, `must_have_topics`

**Выход:** `List[str]` — 15–25 английских LSI-слов.

**Особенности:**
- Английский язык: LSI используется в основном для поиска картинок (Pixabay/Unsplash лучше работают по-английски).
- Один вызов на статью, кэшируется через `agent_cache`.

### 8.3. `brief_agent` (Sonnet)

**Задача:** сформировать структурированное ТЗ (Brief) на основе анализа конкурентов и введённых пользователем параметров.

**Входы:**
- `article_input`
- `competitor_report`

**Выход:** `Brief`.

**Ключевая функция:** `_compute_target_word_count(article_input, competitor_report)`:
```python
strategy_multipliers = {"shorter_top": 0.7, "match_top": 1.0, "longer_top": 1.3}
if length_strategy == "custom":
    return target_word_count
avg = competitor_report.word_count_range.avg
return round(avg * strategy_multipliers[length_strategy])
```

**Особенности:**
- Промпту передаётся уже посчитанная `target_word_count` — LLM просто использует её.
- `required_elements` берутся из `article_input` (без пересборки).
- `lsi_keywords` **не приходят из lsi_agent** в брифе. Они кладутся в Brief.lsi_keywords **уже в orchestrator** после вызова brief_agent.

### 8.4. `outline_agent` (Sonnet)

**Задача:** составить структуру статьи (H1 + список секций с id, title, level, purpose, target_word_count, keywords, must_cover). Опционально — блок FAQ (`faq_section.enabled`).

**Входы:**
- `article_input`
- `brief`
- `competitor_report`

**Выход:** `Outline`.

**Особенности:**
- Секции могут быть H2 или H3, id формата `s0`, `s1`, `s1_1`, `s2`, ...
- `s0` часто зарезервирован под `quick_answer` (без заголовка H2, идёт сразу после H1).
- Сумма `target_word_count` секций даёт общую длину статьи.
- Проверяет что все `required_elements` из Brief покрыты секциями.

### 8.5. `archetype_picker_agent` (Haiku)

**Задача:** по теме и main_keyword предложить наиболее подходящий archetype из справочника `archetypes` в БД.

**Входы:** `article_title`, `main_keyword`, `niche_id` (из выбранного сайта).

**Выход:** `{suggested_archetype_id, alternatives}`.

**Особенности:**
- Вызывается во время подготовки review-панели.
- Пользователь может подтвердить или выбрать другой — фиксируется в `archetype_picks`.
- В query включаются все архетипы своей ниши.

### 8.6. `style_extractor_agent` (Haiku)

**Задача:** из введённого пользователем текста-референса (несколько абзацев реального писателя) извлечь стилевые характеристики: `style`, `tone`, `age_image`.

**Входы:**
- Reference name.
- Reference text (несколько абзацев).

**Выход:** `{extracted_style, extracted_tone, extracted_age_image}`.

**Особенности:**
- Вызывается один раз при добавлении style_reference в БД.
- Результат сохраняется в `style_references` table.
- Дальнейшие статьи с этим референсом используют кэшированный результат.

### 8.7. `writer_agent` (Sonnet)

**Задача:** написать одну секцию статьи (по одной `SectionSpec`).

**Входы:**
- `article_input`, `brief` — общий контекст.
- `section_spec` — задание на секцию (title, purpose, must_cover, keywords, target_word_count).
- `author` (опционально) — из БД (character, tone, age_image).
- `previous_sections_summary` — краткие резюме уже написанных секций (для консистентности фактов).
- `lsi_keywords`.

**Выход:** markdown секции + маркер `<!-- SUMMARY: ... -->` в конце (для передачи следующей секции).

**Особенности:**
- Промпт содержит блок «АВТОР СТАТЬИ» — жёсткое требование выдерживать голос.
- Промпт содержит правила: не использовать `forbidden_words`, соблюдать `target_word_count ±15%`, использовать LSI естественно.
- Может вставлять плейсхолдер `<!-- IMAGE: описание -->` — image_finder их подхватит.

### 8.8. `critic_agent` (Sonnet)

**Задача:** оценить написанную секцию по 6 критериям (0–100 каждый) и вернуть конкретные claims для правки (если оценка ниже порога).

**Критерии:**
- `content_quality`
- `keyword_usage`
- `structure`
- `factuality`
- `readability`
- `alignment_with_brief`

**Выход:** `CriticFeedback` (score, per_criterion, issues, suggestions).

**Особенности:**
- Использует Sonnet (не Haiku): на Haiku слишком строг, все секции валит.
- Промпт содержит калибровку шкалы: 60+ — публикабельно, ниже 40 — переписать.

### 8.9. `editor_agent` (Sonnet)

**Задача:** переписать секцию с учётом претензий Critic'а.

**Входы:**
- Оригинальный текст секции.
- `CriticFeedback`.

**Выход:** новый текст секции.

**Особенности:**
- Editor **не заменяет Writer** — работает после негативной оценки Critic. Пайплайн: Writer → Critic → (если fail) Editor → Critic → (если fail) Editor → Critic → максимум 3 итерации.

### 8.10. `image_finder_agent` (Haiku внутри для ключей)

**Задача:** найти и вставить картинки в готовый markdown статьи.

**Внутренние этапы:**
1. **Поиск точек вставки** — плейсхолдеры от Writer'а (`<!-- IMAGE -->`) + автоматически после каждого H2/H3 (интервал ~250 слов, мин. секция 60 слов, исключены секции с заголовками «FAQ», «Заключение», «Источники»).
2. **Генерация 10 английских ключей** — через `image_keys_agent` (Haiku), результат кэшируется по `main_keyword` в `data/image_keys_cache.json`.
3. **Поиск** — для каждой точки: Pixabay → Unsplash → Wikimedia. Дедупликация по URL через `used_urls` set.
4. **Скачивание и обработка** — через `image_processor.py`:
   - Resize до 1920 по длинной стороне.
   - Crop 16:9 из центра.
   - Конвертация в WebP quality=70.
   - Сохранение в `<article_dir>/images/N.webp`.
5. **Вставка в markdown** — относительный путь + подпись с источником: `![alt](images/1.webp)\n*Источник: [название](url)*`.

**Особенности:**
- Для превью в QtWebEngine относительные пути не работают — UI перед рендером делает подмену на base64 data: URI (см. UI-раздел).

### 8.11. `faq_writer_agent` (Sonnet)

**Задача:** сгенерировать блок FAQ (## FAQ + вопросы/ответы) по вопросам из `outline.faq_section.questions`.

**Входы:**
- `article_input`, `brief`, готовая статья (markdown).
- Список вопросов.
- Автор (опционально).

**Выход:** markdown-блок FAQ.

**Особенности:**
- Ответы 40–60 слов, прямой ответ первым предложением (для Google featured snippet).
- Стиль автора выдерживается.
- Факты сверяются с контекстом статьи + `brief.must_cover` (эталонные формулировки).
- Вставляется перед секцией «Заключение» через regex-поиск `^##\s+(заключен|итог|подводя|conclusion)`.

### 8.12. `final_qa_agent` (Sonnet + код)

**Задача:** оценить готовую статью по 9 критериям и вернуть QAResult.

**Гибридная оценка:**
- **Код (`qa_metrics.calc_code_metrics`)** считает 6 из 9 критериев:
  - `length_control` (0–100): 100 если в диапазоне ±10% от target, снижается плавно.
  - `completeness`: доля найденных `required_elements` в тексте (по паттернам).
  - `keyword_usage`: main density * 0.7 + secondary coverage * 0.3.
  - `structure`: наличие H1, введения, H2, H3.
  - `readability`: доля предложений >20 слов и <8 слов.
  - `lsi_coverage`: доля LSI-слов, найденных в тексте (по корням).
- **LLM оценивает 3 субъективных:** `brief_alignment`, `intent_coverage`, `factuality`.

**Веса критериев (WEIGHTS в final_qa_agent.py):**
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

**Итоговый score:** взвешенная сумма всех 9. Статус:
- `pass` if score ≥ `QA_SCORE_PASS` (85).
- `pass_with_warnings` if score ≥ `QA_SCORE_WARN` (70).
- `fail` иначе.

**LLM-промпт содержит калибровку:** «70–85 нормальное состояние, ниже 50 непригодно, не сваливайся в 0 из-за одной проблемы».

### 8.13. `metadata_agent` (Sonnet)

**Задача:** сформировать финальный пакет метаданных для публикации.

**Входы:** `full_draft`, `brief`, `outline`, `article_input`.

**Выход:** `FinalPackage`:
- `slug` (URL-friendly).
- `meta_title` (до 60 символов).
- `meta_description` (до 160 символов).
- `tags` (5–10 штук).
- `category`.
- `internal_links_suggestions` — 3–5 тем, на которые стоит поставить внутренние ссылки.
- `schema_data` — JSON-LD FAQPage (если есть FAQ).

---

## 9. Сервисы (общая функциональность)

### `services/serp_loader.py` + `serp_cache.py`

**Задача:** получить SERP-бандл (топ-10 из Google) по запросу.

**Логика:**
- `load_from_cache(main_keyword, geo, language)` — проверяет `data/serp_cache/<hash>.json`.
- Если нет / `force_refresh_serp=True` — HTTP GET на XMLStock API (`XMLSTOCK_API_URL` из .env).
- Ответ содержит топ-10 URLs + распарсенный main content каждого.
- Кэшируется без TTL (SERP меняется медленно; при необходимости — `force_refresh_serp=True`).

### `services/agent_cache.py`

**Задача:** кэшировать результаты вызовов агентов (competitor_analysis, brief, outline, lsi).

**Ключ:** `hash(agent_name + article_title + main_keyword + sorted(secondary_keywords))`.

**Формат:** `data/agent_cache/<agent_name>/<hash>.json`.

**Использование в оркестраторе:**
```python
cached = agent_cache.get("brief_agent", article_input)
if cached:
    brief = Brief.model_validate(cached)
else:
    brief = self.brief_agent.run(article_input, competitor_report)
    agent_cache.save("brief_agent", article_input, brief.to_dict())
```

### `services/qa_metrics.py`

**Задача:** посчитать 6 из 9 QA-критериев без LLM.

**Основные функции:**
- `calc_code_metrics(text, target_words, main_keyword, ...)` — возвращает `CodeMetrics(dataclass)`.
- `_element_present(text, element)` — проверяет наличие `required_elements` по regex.
- `_secondary_coverage_score(text, secondary_keywords)` — покрытие второстепенных.
- `_lsi_coverage_score(text, lsi_keywords)` — покрытие LSI.
- `_readability_score(text)` — доля длинных/коротких предложений.

**Особенности:**
- `_element_present` нормализует ключ: `"quick_answer — блок ..."` → `"quick_answer"`.
- Паттерны для `_ELEMENT_PATTERNS`: свой набор regex для каждого required_element.
- Стоп-слова только русские (`_STOPWORDS = {"в", "на", "у", ...}`) — для многоязычности потребует расширения.

### `services/image_finder/` — модуль провайдеров картинок

**Файлы:**
- `base.py` — интерфейс `ImageProvider` (search, download).
- `pixabay.py` — Pixabay API, поддержка 10 ключей с ротацией при rate-limit.
- `unsplash.py` — Unsplash API, 10 ключей.
- `wikimedia.py` — Wikimedia Commons (без ключа).
- `__init__.py` — `get_providers()` → упорядоченный список.

**Ротация ключей:** при HTTP 429 (rate limit) — след. ключ. Все ключи исчерпаны — провайдер помечен исчерпанным до перезапуска.

### `services/image_processor.py`

**Задача:** скачать картинку, обрезать 16:9 из центра, конвертировать в WebP.

**Функция:** `process_image(url, output_path)` → `dict` с метаданными (size, dimensions).

Работает через Pillow. WebP quality=70, target dimensions 1280×720.

### `services/markdown_builder.py`

**Задача:** собрать финальный markdown из `Outline` + финальные тексты секций.

**Функция:** `assemble_draft(outline, final_sections)` → `FullDraft`.

**Особенности:**
- Определяет "no-heading sections" — их title не рендерится (например, `quick_answer` — сразу после H1 идёт текст).
- Убирает `<!-- SUMMARY: ... -->` из финального текста.
- Проверяет наличие FAQ-секции в `outline.sections` для решения, будет ли шаг 9 (faq_writer_agent).

### `services/cost_tracker.py`

**Задача:** отслеживать стоимость LLM-вызовов.

**Особенности:**
- Считает по `MODEL_PRICES` из `llm_settings.py`.
- Суммирует в `articles.cost_usd` в БД.
- Передаёт realtime через колбэк в UI (для отображения "$0.045 за эту статью").

### `services/archetype_matcher.py`

**Задача:** внутри review-панели показать релевантные архетипы для темы + подсветить suggestion от `archetype_picker_agent`.

### `services/input_normalizer.py`

**Задача:** нормализация введённых пользователем данных перед созданием `ArticleInput`:
- Обрезка пробелов.
- Удаление дублей в списках.
- Валидация языка/гео/интента.

### `services/intent_detector.py`

**Задача:** по main_keyword определить intent (`informational` / `how_to`) — на случай если пользователь не задал.

### `services/json_parser.py`

**Задача:** снять обёртки `​`​`​`json / `​`​`​` из ответа LLM и распарсить. Используется во всех агентах.

### `services/retry_service.py`

**Задача:** экспоненциальный retry с backoff при ошибках API. Уважает `stop_flag`.

### `services/translation_cache.py`

**Задача:** кэш переводов (для image_finder — main_keyword переводится на английский). Ключ — исходная строка + пара языков.

### `services/word_count_service.py`

**Задача:** унифицированный подсчёт слов (учитывает markdown, картинки, HTML-теги).

### `services/serp_analyzer.py` (deprecated)

Устаревший модуль, помечен в бэклоге на удаление.

---

## 10. Кэширование

### 4 уровня кэша

| Кэш | Файл / место | Ключ | TTL |
|---|---|---|---|
| SERP | `data/serp_cache/<hash>.json` | main_keyword + geo + language | без TTL |
| Agent | `data/agent_cache/<agent>/<hash>.json` | agent + title + keyword + secondary | без TTL |
| Image keys | `data/image_keys_cache.json` | main_keyword (нижний регистр) | без TTL |
| Translation | `data/translation_cache.json` | text + src + dst languages | без TTL |
| Style ref | БД `style_references.extracted_*` | reference_id | до deactive |

### Инвалидация
- `force_refresh_serp=True` в `ArticleInput` — обновляет SERP.
- Ручное удаление файлов кэша (кнопки в UI нет).

### Что НЕ кэшируется
- Writer / Critic / Editor — каждый вызов новый (даже для одной секции).
- FAQ Writer — каждый раз.
- Final QA — каждый раз.
- Metadata — каждый раз.
- Image search — API-вызов каждый раз (но с 10-ключами ротация справляется).

---

## 11. UI-архитектура

Всё UI — в единственном файле `app/ui/main_window.py` (~3185 строк).

### Общая структура

```python
class MainWindow(QMainWindow):
    def _build_ui(self):
        # Создаёт QWebEngineView, встраивает в него _build_html()
        # Подключает WebChannel с bridge-объектом AppBridge
        # setHtml с baseUrl="qrc:/"
```

### Bridge (Python ↔ JS)

Класс `AppBridge(QObject)` содержит `@Slot`-методы, которые вызываются из JS через `bridge.methodName(...)`. Обратно — Python вызывает JS через `webView.page().runJavaScript("...")`.

**Ключевые слоты (Python-side):**
- `runPipeline(article_input_json)` — запуск пайплайна.
- `stopPipeline()` — остановка.
- `resumeWithOutline(outline_json)` — продолжить после review.
- `getArticles()` → JSON списка статей.
- `getSites()`, `getAuthors()`, `getNiches()`, `getArchetypes()`.
- `getArticleResult(article_id)` → результат для страницы «Результат» (включая `article_markdown_preview` с base64-картинками).
- `getAnalyticsData()` — статистика для страницы «Аналитика».
- `createSite(...)`, `deleteSite(domain)`, `createAuthor(...)`.
- `extractStyleForReference(name, text)` — для добавления референса.
- `openArticleFolder(article_id)`.
- `copyToClipboard(text)`.

**Ключевые сигналы (Python → JS через runJavaScript):**
- `uiPipelineStarted()` — блокирует форму, показывает Stop.
- `uiPipelineStep(step_name, status)` — обновляет прогресс.
- `uiLogEntry(msg, type)` — добавляет строку в лог-панель.
- `uiPromptCaptured(step, prompt, response)` — для панели «Диалог агентов».
- `uiReviewReady(data)` — открывает review-панель.
- `uiPipelineFinished(qa_result, final_package, article_id)` — заполняет результат.
- `uiPipelineError(msg)` — показывает ошибку.
- `updateCost(article, session, last, total)` — обновляет счётчики.
- `uiSectionUpdate(section_id, status, iter, word_count)`.
- `uiArticleAborted(reason)`.

### Страницы (SPA)

Все страницы в одном HTML. Переключение через `showPage(name)`:
- `page-form` — форма создания статьи (Главная).
- `page-monitor` — монитор генерации.
- `page-result` — заглушка для «Результат» (реальный контент внутри `page-monitor` в вкладке `panel-result`).
- `page-history` — история всех статей.
- `page-sites` — сайты + авторы + референсы.
- `page-analytics` — аналитика.

### Боковая панель (nav-sidebar)

Всегда видна. Три шага:
- 🏠 Главная (→ `page-form`)
- ✍️ Написание (→ `page-monitor`)
- ✅ Результат (→ `page-result` или `page-monitor` с вкладкой `panel-result`)

### Топбар

- Слева: SEO Pipeline title + статус + счётчики стоимости.
- Справа (только на Главной, класс `.tb-home-only`): Сайты / Аналитика / История.
- Всегда: Stop (во время генерации), Copy / Open Folder (после генерации).

### Форма создания статьи

Основные поля:
- Сайт (dropdown, тестовые внизу).
- Автор (dropdown, зависит от сайта).
- Тема статьи, main_keyword, secondary_keywords (textarea, one per line).
- Стратегия объёма (радио-группа: shorter/match/longer/custom).
- Язык (ru/en/de/...), Гео, Интент, Тип, Сложность.
- Стилевой архетип.
- Запрещённые слова, дополнительные заметки.
- Чекбоксы обязательных элементов: faq, quick_answer, table, list, conclusion, sources_block.
- Чекбокс `always_review_sections` (пауза после outline).

### Мониторинг генерации

Разделён на три вкладки:
1. **Лог** — построчный лог событий с временем.
2. **Диалог агентов** — раскрывающиеся блоки с промптами и ответами каждого LLM-вызова.
3. **Результат** — QA-score с детализацией, meta_title, meta_description, preview markdown.

Слева боковая панель показывает прогресс шагов + секций.

### Review-панель (пауза)

Открывается после Шага 5, если `always_review_sections=True`. Внутри:
- Слева: сводка конкурентов (word_count avg/min/max, h2 avg, common H2, must-have topics), точки роста (с чекбоксами — можно принять в outline).
- Справа: редактируемый outline (H1 + список секций, каждую можно править / удалить / добавить), suggestion архетипа с альтернативами.
- Внизу: сумма слов по секциям, кнопки «Отменить» и «Продолжить».

При клике «Продолжить» — вызывается `bridge.resumeWithOutline(outline_data)`.

### Предпросмотр статьи

Внутри страницы результата — переключатель Markdown / Rendered. Renderer использует `marked.js` (загружается с CDN cloudflare).

Для показа картинок:
- В файле `article.md` — относительные пути `images/1.webp`.
- При загрузке в UI (`getArticleResult` в Python) — прямо в Python-слоте картинки конвертируются в `data:image/webp;base64,...` и подставляются в `article_markdown_preview` (отдельное поле в ответе). Копирование берёт оригинал с относительными путями.

Этот подход обходит проблему cross-origin: страница загружена с `qrc://`, а `file://` картинки блокируются даже с `LocalContentCanAccessFileUrls=True`.

### Стили

Все в одном `<style>`-блоке в HTML. Основа — тёмная тема (Catppuccin-inspired):
- Фон: `#1e1e2e`
- Панель: `#181825`
- Границы: `#313244`
- Основной текст: `#cdd6f4`
- Акцент: `#89b4fa` (синий)
- Успех: `#a6e3a1`
- Предупреждение: `#f9e2af`
- Ошибка: `#f38ba8`

Layout использует `grid` для основного layout (nav-sidebar + main content).

---

## 12. Внешние интеграции

### 12.1. Anthropic Claude API

- **Модели:** Sonnet 4.6 (основная), Haiku 4.5 (короткие задачи).
- **API:** `anthropic` Python SDK.
- **Ключ:** `ANTHROPIC_API_KEY` в .env.
- **Retry:** экспоненциальный backoff при 429/500 через `retry_service`.
- **Стоимость:** одна средняя статья — $0.04–$0.10.

### 12.2. XMLStock SERP API

- **URL:** `http://95.217.108.20:8085/api/v1/parsers/xmlstock/serp` (self-hosted).
- **Задача:** топ-10 URLs по запросу для Google, с распарсенным main content.
- **Ключ:** не требуется (self-hosted).
- **Ответ:** JSON с массивом `[{url, title, description, text, ...}, ...]`.

### 12.3. Pixabay API

- **URL:** `https://pixabay.com/api/`.
- **Ключи:** до 10 штук в `PIXABAY_API_KEYS` (comma-separated).
- **Ротация:** при 429 — следующий ключ.
- **Использование:** первый провайдер картинок.

### 12.4. Unsplash API

- **URL:** `https://api.unsplash.com/search/photos`.
- **Ключи:** до 10 штук в `UNSPLASH_ACCESS_KEYS`.
- **Использование:** второй провайдер после Pixabay.

### 12.5. Wikimedia Commons

- **URL:** `https://commons.wikimedia.org/w/api.php`.
- **Ключ:** не требуется.
- **Использование:** третий провайдер (fallback).

### 12.6. Отсутствующие / зарезервированные

- **OpenAI** — импортирован, но не используется. Может понадобиться для fine-tuning в будущем.
- **Google Gemini** — импортирован, но не используется (был у Writer/Editor, отключён из-за региональной блокировки).

---

## 13. Конфигурация и переменные окружения

Все настройки — в `.env` файле в корне проекта. Пример — `env.example`.

### Переменные

```dotenv
# API ключи LLM
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GOOGLE_API_KEY=your_google_gemini_key_here

# PostgreSQL
DATABASE_URL=postgresql://postgres:password@localhost:5432/seo_pipeline

# XMLStock SERP API
XMLSTOCK_API_URL=http://95.217.108.20:8085/api/v1/parsers/xmlstock/serp

# Ключи картинок (по 10 на провайдера, через запятую)
PIXABAY_API_KEYS=key1,key2,...
UNSPLASH_ACCESS_KEYS=key1,key2,...
```

### Config-файлы Python

- `app/config/settings.py` — пути, версии.
- `app/config/llm_settings.py` — модели, цены, параметры вызовов.
- `app/config/pipeline_settings.py` — статусы, пороги QA, итерации Critic.
- `app/config/prompt_settings.py` — `PROMPT_REGISTRY` — маппинг agent_name → путь к промпту.

### Версионирование промптов

`PROMPT_VERSION = "v1"` в `prompt_settings.py`. Промпты хранятся в `prompts/<agent_name>/v1.txt`. Возможно добавление v2 для A/B-тестов.

---

## 14. Логирование и отладка

### Python logging

Настройка через стандартный `logging`. Основной формат:
```
[YYYY-MM-DD HH:MM:SS] LEVEL module: message
```

Файл лога: `logs/app_YYYY-MM-DD.log`.

Основные логгеры:
- `app.main` — старт/стоп.
- `app.storage.db_manager` — БД.
- `app.orchestrator.pipeline_orchestrator` — шаги пайплайна.
- `app.agents.*` — каждый агент отдельно.

### JS console

`_ExternalLinkPage.javaScriptConsoleMessage` перенаправляет console.log/error из JS в Python logging с указанием строки и файла.

### Промпты на диске

Каждый вызов LLM пишется в `data/articles/<article_dir>/prompts/`:
- `<step_name>_prompt.txt` — что ушло в LLM.
- `<step_name>_response.txt` — что вернулось.

Помогает при отладке некачественных генераций.

---

## 15. Известные ограничения и особенности

### 15.1. Многоязычность
- Реализована для промптов Writer'а (принимает `$language`), но не полностью.
- QA-метрики (стоп-слова, sentence-splitter) настроены под русский.
- Каталог референсов писателей — только русские.
- Целевая поддержка (в бэклоге для миграции): en, de, it, es, fr — как обязательный контур.

### 15.2. AVG длины конкурентов искажается outlier'ами
- Википедия часто в топе с 10000+ слов, это искажает `word_count_range.avg` в 2–3 раза.
- В бэклоге: перейти на медиану или trimmed mean.

### 15.3. Length control не всегда справедливый
- Считается от `brief.word_count_target`, но реальная целевая длина — сумма `target_word_count` секций outline.
- В бэклоге: переключить QA на сумму outline.sections.

### 15.4. Кэш ключ не покрывает всё
- Не включает `language`, `geo`, `intent` — они всегда жёстко связаны с темой.
- Не покрывает изменения промпта (новая версия промпта требует ручной инвалидации кэша).

### 15.5. Дубли FAQ (недавний баг)
- Если Writer генерирует секцию с `title="FAQ — ..."`, а в outline также `faq_section.enabled=True` — получаем два FAQ.
- Исправление: проверять `title.lower().contains("faq")` в `has_faq_in_sections` (сделано в последней сессии).

### 15.6. UI-баги
- Review-панель обрезается снизу при большом объёме контента.
- Автоскролл при каждом обновлении шагов.
- Индикатор активного шага в боковой панели не всегда синхронизирован.

### 15.7. Fact-checking — только LLM-эвристика
- Нет обращения к внешним источникам (Wikipedia, Wikidata).
- LLM в критике оценивает factuality "на ощущение" — попадаются галлюцинации.

### 15.8. QA warnings — плоский список
- Нет разделения на критичные / средние / незначительные.
- В UI отображаются одним общим блоком.

### 15.9. main_window.py — 3000+ строк
- В одном файле: HTML, CSS, JS, Python-Slot bridge, все страницы, все обработчики.
- Планируется рефакторинг — раздельные модули по страницам.

### 15.10. Docker и веб-версия отсутствуют
- Приложение только настольное.
- Веб-версия — большая задача в бэклоге (см. миграцию на FastAPI + Celery + Docker).

### 15.11. Публикация вручную
- Приложение генерирует markdown + метаданные, но не публикует.
- WordPress API-интеграция в бэклоге.

### 15.12. Отсутствие fine-tuning
- Anthropic не даёт fine-tuning через публичный API.
- Возможные пути "самообучения" (в бэклоге):
  - Feedback loop от QA (автокоррекция параметров).
  - База проверенных фактов.
  - Каталог удачных outline.
  - RAG (векторный индекс по сгенерированным статьям + внешним источникам).

### 15.13. Ограничения контекста Sonnet
- Максимум ~200K токенов на вызов.
- В теории может стать проблемой для очень больших SERP-бандлов — сейчас смягчено передачей только выжимок конкурентов, а не полных текстов.

### 15.14. Cost tracking неточен для Google/OpenAI
- В `MODEL_PRICES` есть цены Gemini и GPT, но эти модели не используются.
- Считается только Claude — что покрывает 100% текущих вызовов.

---

## Приложения

### Приложение A. Полный список статусов пайплайна

Из `app/config/pipeline_settings.py`:
- `created`
- `input_validated`
- `serp_done`
- `competitor_analysis_done`
- `brief_done`
- `outline_done`
- `sections_in_progress`
- `draft_ready`
- `qa_done`
- `completed`
- `ready_for_manual_review`
- `ready_for_manual_review_with_warnings`
- `failed`
- `stopped_by_user`

### Приложение B. Полный список required_elements

Разрешено в `article_input.required_elements`:
- `faq`
- `quick_answer`
- `table`
- `list`
- `conclusion`
- `sources_block`

### Приложение C. Полный список ниш

- `travel` — Трэвел / путешествия
- `home` — Дом / ремонт / быт
- `auto` — Авто-эксплуатация
- `lifestyle` — ЗОЖ / lifestyle
- `pets` — Питомцы
- `garden` — Сад / дача
- `utility` — Образовательный utilitarian-контент

### Приложение D. Полный перечень архетипов

**Travel:** destination-guide, route, top-list, comparison, personal, practical-guide.
**Home:** full-guide, comparison, howto-diy, product-review, top-list, calculation-guide.
**Auto:** operation-guide, diagnostic-howto, comparison, choose-guide, faq-list.
**Lifestyle:** habit-guide, comparison, myth-vs-fact, practical-tips, self-check-list.
**Pets:** care-guide, breed-guide, howto, product-review.
**Garden:** plant-guide, seasonal-howto, problem-solution, comparison.
**Utility:** step-by-step, comparison, error-fix, quick-answer.

---

**Конец документа.**
