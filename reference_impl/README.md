# SEO Pipeline — Генератор SEO-статей

Многоэтапный AI-пайплайн для автоматической генерации SEO-статей на основе анализа поисковой выдачи.

## Архитектура

```
Входные данные (GUI)
  → SERP-анализ (XMLStock API + readability + TF-IDF)
  → Анализ конкурентов (Claude)
  → Формирование ТЗ (Claude)
  → Структура статьи (Claude)
  → Написание секций (Gemini 2.5 Pro) + Проверка (Claude) + Правка (Gemini)
  → Сборка статьи
  → Финальный QA (Claude)
  → Метаданные (Claude)
  → Сохранение результата
```

## Установка

### 1. Требования
- Python 3.10+
- API-ключи: Anthropic, Google AI (Gemini)

### 2. Клонировать и установить зависимости

```bash
git clone <repo>
cd seo_pipeline
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Настроить API-ключи

```bash
cp .env.example .env
```

Отредактировать `.env`:
```
OPENAI_API_KEY=sk-...          # опционально
ANTHROPIC_API_KEY=sk-ant-...   # обязательно
GOOGLE_API_KEY=AIza...         # обязательно
```

### 4. Запустить

```bash
python run.py
```

## Структура проекта

```
seo_pipeline/
├── run.py                      # Точка входа
├── requirements.txt
├── .env.example
│
├── app/
│   ├── main.py                 # Инициализация + запуск GUI
│   │
│   ├── config/                 # Настройки
│   │   ├── settings.py         # Пути, API-ключи
│   │   ├── llm_settings.py     # Модели по агентам
│   │   ├── pipeline_settings.py # Лимиты, статусы
│   │   └── prompt_settings.py  # Пути к промптам
│   │
│   ├── schemas/                # Pydantic-схемы данных
│   │   ├── article_input.py
│   │   ├── serp_bundle.py
│   │   ├── competitor_analysis_report.py
│   │   ├── brief.py
│   │   ├── outline.py
│   │   ├── section_schemas.py
│   │   └── output_schemas.py   # FullDraft, QAResult, FinalPackage
│   │
│   ├── agents/                 # AI-агенты
│   │   ├── competitor_analysis_agent.py  → Claude
│   │   ├── brief_agent.py                → Claude
│   │   ├── outline_agent.py              → Claude
│   │   ├── writer_agent.py               → Gemini 2.5 Pro
│   │   ├── critic_agent.py               → Claude
│   │   ├── editor_agent.py               → Gemini 2.5 Pro
│   │   ├── final_qa_agent.py             → Claude
│   │   └── metadata_agent.py             → Claude
│   │
│   ├── llm/
│   │   └── llm_client.py       # Единый клиент: Anthropic / OpenAI / Google
│   │
│   ├── orchestrator/
│   │   ├── pipeline_orchestrator.py  # Главный координатор
│   │   ├── section_pipeline.py       # Цикл write→critic→edit
│   │   └── status_manager.py         # Управление статусами
│   │
│   ├── services/
│   │   ├── serp_analyzer.py     # SERP + readability + TF-IDF
│   │   ├── input_normalizer.py  # Нормализация входных данных
│   │   ├── markdown_builder.py  # Сборка markdown из секций
│   │   ├── json_parser.py       # Парсинг JSON из LLM-ответов
│   │   ├── retry_service.py     # Retry-логика
│   │   └── word_count_service.py
│   │
│   ├── storage/
│   │   ├── sqlite_manager.py    # Подключение к SQLite
│   │   ├── repositories.py      # CRUD-операции
│   │   ├── file_storage.py      # Файловое хранилище
│   │   └── artifact_manager.py  # Фасад для сохранения артефактов
│   │
│   ├── utils/
│   │   ├── ids.py
│   │   ├── text_utils.py
│   │   ├── time_utils.py
│   │   └── file_utils.py
│   │
│   └── ui/
│       ├── main_window.py       # Главное окно
│       ├── article_form.py      # Форма ввода
│       ├── article_list.py      # Список статей
│       ├── pipeline_panel.py    # Статусы шагов
│       └── logs_panel.py        # Лог / Prompt / Response / JSON / Результат
│
├── prompts/                     # Тексты промптов
│   ├── competitor_analysis_agent/v1.txt
│   ├── brief_agent/v1.txt
│   ├── outline_agent/v1.txt
│   ├── writer_agent/v1.txt
│   ├── critic_agent/v1.txt
│   ├── editor_agent/v1.txt
│   ├── final_qa_agent/v1.txt
│   └── metadata_agent/v1.txt
│
├── data/                        # Данные (создаётся автоматически)
│   ├── app.db                   # SQLite
│   └── articles/
│       └── {article_id}/
│           ├── article_input.json
│           ├── serp_bundle.json
│           ├── competitor_analysis_report.json
│           ├── brief.json
│           ├── outline.json
│           ├── sections/
│           │   ├── s1_draft.json
│           │   ├── s1_review_1.json
│           │   └── s1_final.json
│           ├── full_draft.json
│           ├── article.md          ← готовая статья
│           ├── qa_result.json
│           ├── final_package.json
│           ├── logs/
│           │   └── pipeline.log
│           └── prompts/
│               ├── brief_generation_prompt.txt
│               └── brief_generation_response.txt
│
└── logs/
    └── app.log
```

## Используемые модели

| Агент | Модель | Роль |
|-------|--------|------|
| competitor_analysis_agent | Claude Sonnet | Анализ SERP-данных |
| brief_agent | Claude Sonnet | Формирование ТЗ |
| outline_agent | Claude Sonnet | Структура статьи |
| writer_agent | Gemini 2.5 Pro | Написание секций |
| critic_agent | Claude Sonnet | Проверка текста |
| editor_agent | Gemini 2.5 Pro | Редактура секций |
| final_qa_agent | Claude Sonnet | Оценка качества |
| metadata_agent | Claude Sonnet | Метаданные |

## Где лежат промпты

`prompts/{agent_name}/v1.txt` — версионированные текстовые шаблоны.
Переменные подставляются через `$variable` синтаксис.

## Смена модели

В `app/config/llm_settings.py` → `AGENT_MODELS` поменять `model` и `provider` для любого агента.

## Результат работы

Каждая статья сохраняется в `data/articles/{article_id}/`:
- `article.md` — готовая статья в Markdown
- `final_package.json` — slug, meta_title, meta_description, FAQ, schema, tags
- `qa_result.json` — оценка качества 0–100 с критериями
- `prompts/` — все промпты и ответы моделей для дебага

## Стоимость (~$4–6 за статью)

Основные затраты: Gemini 2.5 Pro (написание контента) + Claude Sonnet (аналитика и QA).
