# LEGACY_FORMAT.md — соответствие desktop-формата и ТЗ раздел 13

Реальные примеры (`fixtures/`, `reference_article/`) сохранены **desktop-версией**
и в ряде полей расходятся с ТЗ раздел 13. Схемы §13 объявлены строго по ТЗ и не
меняются; вся нормализация legacy → §13 собрана в одном модуле
`backend/app/schemas/legacy_compat.py` и применяется **только на входе**
(Pydantic `mode="before"`). Выходной контракт пайплайна — строго §13 (тест
`backend/tests/test_output_contract.py`).

## Таблица соответствий (legacy desktop → ТЗ §13)

| Схема (§13) | Поле | Legacy desktop | §13 | Правило нормализации | Тип |
|---|---|---|---|---|---|
| ArticleInput (13.1) | `required_elements[*]` | `sources_block` | `weaved_sources` | элемент переименовывается; список дедуплицируется и чистится от пустых | breaking |
| WordCountRange (13.2) | среднее | `avg` | `avg_trimmed` | если `avg_trimmed` не задан — берётся `avg` | lossy |
| DataSensitivity (13.2) | волатильность | `time_sensitive` | `has_volatile_data` | ключ переименовывается | lossy |
| DataSensitivity (13.2) | — | `avoid_exact_dates` | *(нет)* | отбрасывается: в §13 директива вынесена в `Brief.data_handling_rules` | lossy |
| QAResult (13.8) | `warnings` | `list[str]` (плоский) | `QAWarnings{critical,medium,minor}` | список целиком → `medium` (не critical: fail_reasons отдельно) | breaking |

«breaking» — без нормализации строгая §13-схема падает с `ValidationError`;
«lossy» — файл бы распарсился (лишние ключи игнорируются), но реальные данные
потерялись бы молча.

## Форматы вне ТЗ §13 (следуем реальным файлам)

| Файл(ы) | Схема | Примечание |
|---|---|---|
| `fixtures/serp_bundle_example.json`, `reference_article/serp_bundle.json` | `SerpBundle` (`schemas/serp.py`) | Структура по реальному desktop-формату (`urls/pages/aggregated/analysis_csv/contents_txt`). Snippet в ТЗ §6.3 иллюстративен и не является каноном. |
| `fixtures/lsi_example.json` | `LSIResult` (`schemas/misc.py`) | `{lsi_keywords: [...]}` |
| `fixtures/review_data_example.json` | `ReviewData` (`schemas/misc.py`) | payload review-панели: `review_data{competitor,outline,archetype}` |
| `reference_article/sections/*_draft.json`, `*_patched_N.json` | `SectionDraftArtifact` (`schemas/desktop_artifacts.py`) | desktop-черновик секции; web-пайплайн пишет §13.5 `SectionAttempt` |
| `reference_article/sections/*_review_N.json` | `SectionReviewArtifact` (`schemas/desktop_artifacts.py`) | desktop-ревью; web-пайплайн пишет §13.5 `CriticFeedback` |
| `reference_article/sections/*_final.json` | `SectionFinal` (§13.5) | парсится штатно (лишние `word_count`/`is_weak` игнорируются) |

## Правила сопровождения

- Любое новое legacy-правило добавляется **только** в `legacy_compat.py` (не
  размазывать по схемам) и строкой в таблицу выше.
- Валидаторы совместимости в коде помечены комментарием
  `# legacy desktop-format compatibility`.
- Web-пайплайн (T-6+) при записи артефактов использует схемы §13 — legacy-поля
  на выход не пишутся (гарантируется `test_output_contract.py`).
