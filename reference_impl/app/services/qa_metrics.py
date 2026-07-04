"""
qa_metrics.py — детерминированные метрики качества статьи.

Считает 5 критериев кодом без участия LLM:
  - length_control   (отклонение от целевого объёма)
  - completeness     (наличие обязательных элементов)
  - keyword_usage    (плотность главного ключа + покрытие второстепенных)
  - structure        (H1/H2/H3, введение)
  - readability      (длина предложений)

Возвращает dict со значениями 0-100 для каждого критерия.
"""
import re
from dataclasses import dataclass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _count_words(text: str) -> int:
    """Количество слов в тексте."""
    return len(re.findall(r'\b\w+\b', text, re.UNICODE))


def _split_sentences(text: str) -> list[str]:
    """
    Разбивает текст на предложения.
    Убирает markdown-разметку перед разбивкой.
    """
    # Убираем markdown: заголовки, списки, таблицы, ссылки
    clean = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    clean = re.sub(r'^\s*[-*+]\s+', '', clean, flags=re.MULTILINE)
    clean = re.sub(r'^\s*\d+\.\s+', '', clean, flags=re.MULTILINE)
    clean = re.sub(r'\|[^|]+', ' ', clean)          # таблицы
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)  # ссылки
    clean = re.sub(r'[*_`]+', '', clean)            # форматирование
    clean = re.sub(r'\n+', ' ', clean)

    # Разбиваем по . ! ? с учётом аббревиатур
    sentences = re.split(r'(?<=[.!?])\s+(?=[А-ЯЁA-Z«"])', clean)
    # Фильтруем пустые и слишком короткие (артефакты)
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, value))


# ─── 1. length_control ────────────────────────────────────────────────────────

def calc_length_control(text: str, target_words: int) -> float:
    """
    Оценивает попадание в целевой объём.
    Отклонение 0% → 100, >40% → 0.
    """
    if target_words <= 0:
        return 100.0

    actual = _count_words(text)
    deviation = abs(actual - target_words) / target_words

    if deviation <= 0.05:
        score = 100
    elif deviation <= 0.10:
        score = 100 - (deviation - 0.05) / 0.05 * 15   # 100→85
    elif deviation <= 0.20:
        score = 85 - (deviation - 0.10) / 0.10 * 25    # 85→60
    elif deviation <= 0.30:
        score = 60 - (deviation - 0.20) / 0.10 * 30    # 60→30
    elif deviation <= 0.40:
        score = 30 - (deviation - 0.30) / 0.10 * 30    # 30→0
    else:
        score = 0

    return round(_clamp(score), 1)


# ─── 2. completeness ──────────────────────────────────────────────────────────

# Паттерны для каждого обязательного элемента
_ELEMENT_PATTERNS = {
    "faq": [
        r'(?i)^#{1,3}\s*(faq|часто задаваемые|вопрос)',
        r'\?\s*\n',                          # строка оканчивающаяся на ?
    ],
    "quick_answer": [
        # Классический вариант: явный заголовок
        r'(?i)^#{1,3}\s*(быстрый ответ|кратко|tldr|резюме|quick answer)',
        # Или выделенный маркер жирным
        r'(?i)\*\*кратко',
        # SEO-практика: первый абзац после H1 — короткий (2-4 предложения)
        # и содержит прямой ответ. Ищем H1 + сразу первый абзац разумной длины.
        r'(?ms)\A#\s[^\n]+\n+([^#\n][^\n]{50,400})\n',
    ],
    "table": [
        r'^\|.+\|.+\|',                     # markdown таблица
    ],
    "list": [
        r'(?m)^[-*+]\s+\S',                 # маркированный список
        r'(?m)^\d+\.\s+\S',                 # нумерованный список
    ],
    "conclusion": [
        r'(?i)^#{1,3}\s*(заключени|вывод|итог|подводя)',
    ],
    "sources_block": [
        r'(?i)^#{1,3}\s*(источник|литератур|ссылк|references)',
    ],
}

def _normalize_element_key(element: str) -> str:
    """
    Приводит строку обязательного элемента к ключу _ELEMENT_PATTERNS.
    Поддерживает форматы:
      - "faq"
      - "faq — блок из 5-7 вопросов..."
      - "FAQ блок..."
    Берёт первое слово до тире/двоеточия/пробела, lower-case.
    """
    s = element.strip()
    # Отрезаем по первому разделителю
    for sep in (" — ", " - ", ":", " ", "—"):
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    return s.lower().strip()


def _element_present(text: str, element: str) -> bool:
    key = _normalize_element_key(element)
    patterns = _ELEMENT_PATTERNS.get(key, [])
    for pat in patterns:
        if re.search(pat, text, re.MULTILINE | re.UNICODE):
            return True
    return False


def calc_completeness(text: str, required_elements: list[str]) -> float:
    """
    Проверяет наличие обязательных элементов в markdown.
    Каждый элемент равен 100 / len(required_elements) баллов.
    """
    if not required_elements:
        return 100.0

    points_per = 100.0 / len(required_elements)
    score = 0.0

    for elem in required_elements:
        if _element_present(text, elem):
            score += points_per

    return round(_clamp(score), 1)


def completeness_details(text: str, required_elements: list[str]) -> dict[str, bool]:
    """Возвращает словарь {элемент: найден} для отладки."""
    return {e: _element_present(text, e) for e in required_elements}


# ─── 3. keyword_usage ─────────────────────────────────────────────────────────

# Стоп-слова (предлоги, союзы, частицы), которые не считаются содержательными
# словами ключа — их исключаем при покрытии и подсчёте.
_STOPWORDS = {
    "в", "на", "у", "с", "к", "о", "об", "от", "до", "за", "по", "из",
    "и", "а", "но", "или", "же", "ли", "не", "ни",
    "что", "как", "где", "когда", "куда", "почему", "зачем",
    "это", "то", "так", "там", "тут", "тогда",
    "для", "при", "со", "во",
}


def _word_tokens(text: str) -> list[str]:
    """Слова в нижнем регистре, без пунктуации."""
    return [w.lower() for w in re.findall(r'\b[\wа-яёА-ЯЁ]+\b', text, re.UNICODE)]


def _content_words(phrase: str) -> list[str]:
    """Содержательные слова ключа (без предлогов/союзов)."""
    words = [w for w in _word_tokens(phrase) if w not in _STOPWORDS and len(w) > 2]
    return words


def _keyword_density_score(text: str, keyword: str) -> float:
    """
    Оценивает использование главного ключа БЕЗ требования дословного вхождения.

    Логика:
      1. Из ключа достаём содержательные слова (без предлогов/союзов).
      2. Считаем, сколько раз каждое из них встречается в тексте.
      3. Если в тексте присутствуют ВСЕ содержательные слова ключа
         (пусть даже в разных частях текста и разном порядке) — ключ «закрыт».
      4. Плотность считаем как «сколько раз ключ закрыт целиком», что
         эквивалентно минимуму вхождений по содержательным словам.
    """
    if not keyword:
        return 0.0

    content = _content_words(keyword)
    if not content:
        # Ключ состоит только из стоп-слов — нечего считать
        return 70.0

    text_tokens = _word_tokens(text)
    text_lower  = " ".join(text_tokens)
    word_count  = len(text_tokens)
    if word_count == 0:
        return 0.0

    # Сколько раз каждое содержательное слово встречается в тексте
    counts = []
    for w in content:
        # Считаем словосочетания и их формы по корню — простое вхождение
        # по началу слова (учитывает падежи: «байкала», «байкалу»).
        root = w[:max(3, len(w) - 2)]   # отрезаем 1-2 окончания
        pattern = re.compile(rf"\b{re.escape(root)}\w*", re.IGNORECASE | re.UNICODE)
        counts.append(len(pattern.findall(text_lower)))

    # «Полные закрытия» ключа = минимум по содержательным словам
    full_occurrences = min(counts) if counts else 0
    if full_occurrences == 0:
        # Хотя бы одно слово ключа не встретилось — провал
        return 20.0

    words_per_occurrence = word_count / full_occurrences

    if 100 <= words_per_occurrence <= 300:
        return 100.0
    elif 70 <= words_per_occurrence < 100:
        return 85.0
    elif 300 < words_per_occurrence <= 500:
        return 80.0
    elif 50 <= words_per_occurrence < 70:
        return 65.0
    elif words_per_occurrence > 500:
        return 55.0
    else:
        return 35.0   # экстремальный перебор (<50 слов на вхождение)


def _secondary_coverage_score(text: str, secondary_keywords: list[str]) -> float:
    """
    Оценивает покрытие второстепенных ключей.
    Ключ считается покрытым если в тексте есть ВСЕ его содержательные слова
    (необязательно дословно подряд — главное по словам).
    """
    if not secondary_keywords:
        return 100.0

    text_tokens = set(_word_tokens(text))
    # Также проверяем вхождения по корню (для падежей)
    text_lower = " ".join(text_tokens)

    found = 0
    for kw in secondary_keywords:
        content = _content_words(kw)
        if not content:
            found += 1
            continue
        all_present = True
        for w in content:
            root = w[:max(3, len(w) - 2)]
            if not re.search(rf"\b{re.escape(root)}\w*", text_lower, re.IGNORECASE | re.UNICODE):
                all_present = False
                break
        if all_present:
            found += 1

    coverage = found / len(secondary_keywords)

    if coverage >= 0.70:
        return 100.0
    elif coverage >= 0.50:
        return 75.0
    elif coverage >= 0.30:
        return 50.0
    else:
        return 25.0


def calc_keyword_usage(
    text: str,
    main_keyword: str,
    secondary_keywords: list[str],
) -> float:
    """
    Итоговая оценка ключевых слов.
    Главный ключ (70%) + покрытие второстепенных (30%).
    """
    main_score      = _keyword_density_score(text, main_keyword)
    secondary_score = _secondary_coverage_score(text, secondary_keywords)

    score = main_score * 0.7 + secondary_score * 0.3
    return round(_clamp(score), 1)


# ─── 4. structure ─────────────────────────────────────────────────────────────

def calc_structure(text: str) -> float:
    """
    Оценивает структуру markdown-статьи.
    H1 → +20, 3+ H2 → +40, H3 → +20, введение → +20.
    """
    score = 0.0

    # H1
    if re.search(r'^#\s+\S', text, re.MULTILINE):
        score += 20

    # H2 (минимум 3)
    h2_count = len(re.findall(r'^##\s+\S', text, re.MULTILINE))
    if h2_count >= 3:
        score += 40
    elif h2_count == 2:
        score += 25
    elif h2_count == 1:
        score += 10

    # H3
    if re.search(r'^###\s+\S', text, re.MULTILINE):
        score += 20

    # Введение: есть ли текст до первого заголовка H2
    first_h2 = re.search(r'^##\s+', text, re.MULTILINE)
    if first_h2:
        before_h2 = text[:first_h2.start()].strip()
        # Убираем H1 если есть
        before_h2 = re.sub(r'^#\s+.+', '', before_h2, flags=re.MULTILINE).strip()
        if _count_words(before_h2) >= 30:
            score += 20

    return round(_clamp(score), 1)


# ─── 5. readability ───────────────────────────────────────────────────────────

def calc_readability(text: str) -> float:
    """
    Оценивает читаемость текста по длине предложений.

    % предложений > 20 слов:
      0-5%   → 100
      5-10%  → 80
      10-20% → 60
      20-30% → 40
      >30%   → 20

    Штраф за % предложений < 8 слов:
      0-10%  → 0
      10-20% → -10
      >20%   → -20
    """
    sentences = _split_sentences(text)
    if not sentences:
        return 50.0

    total = len(sentences)
    long_count  = sum(1 for s in sentences if _count_words(s) > 20)
    short_count = sum(1 for s in sentences if _count_words(s) < 8)

    pct_long  = long_count  / total
    pct_short = short_count / total

    # Базовый балл по длинным предложениям
    if pct_long <= 0.05:
        base = 100
    elif pct_long <= 0.10:
        base = 80
    elif pct_long <= 0.20:
        base = 60
    elif pct_long <= 0.30:
        base = 40
    else:
        base = 20

    # Штраф за обрубленные предложения
    if pct_short <= 0.10:
        penalty = 0
    elif pct_short <= 0.20:
        penalty = 10
    else:
        penalty = 20

    score = base - penalty
    return round(_clamp(score), 1)


# ─── Публичный интерфейс ──────────────────────────────────────────────────────

@dataclass
class CodeMetrics:
    length_control: float
    completeness:   float
    keyword_usage:  float
    lsi_coverage:   float
    structure:      float
    readability:    float
    details:        dict   # дополнительные детали для лога


def _lsi_coverage_score(text: str, lsi_keywords: list[str]) -> float:
    """
    Оценивает покрытие LSI-слов (тематического словаря).
    Хорошо если 60-80% LSI присутствуют в тексте.
    Полностью аналогично _secondary_coverage_score, но без штрафа за «всего одно слово».
    """
    if not lsi_keywords:
        return 100.0
    text_tokens = set(_word_tokens(text))
    text_lower = " ".join(text_tokens)

    found = 0
    for kw in lsi_keywords:
        content = _content_words(kw)
        if not content:
            found += 1
            continue
        all_present = True
        for w in content:
            root = w[:max(3, len(w) - 2)]
            if not re.search(rf"\b{re.escape(root)}\w*", text_lower, re.IGNORECASE | re.UNICODE):
                all_present = False
                break
        if all_present:
            found += 1

    coverage = found / len(lsi_keywords)
    # Шкала: 60-80% покрытия → 100, ниже — постепенно снижается
    if coverage >= 0.6:
        return 100.0
    elif coverage >= 0.4:
        return 80.0
    elif coverage >= 0.25:
        return 60.0
    elif coverage >= 0.1:
        return 40.0
    return 20.0


def calc_code_metrics(
    text:               str,
    target_words:       int,
    main_keyword:       str,
    secondary_keywords: list[str],
    required_elements:  list[str],
    lsi_keywords:       list[str] = None,
) -> CodeMetrics:
    """
    Считает все детерминированные метрики за один вызов.
    Вызывается из FinalQAAgent перед LLM-вызовом.
    """
    lc = calc_length_control(text, target_words)
    cp = calc_completeness(text, required_elements)
    ku = calc_keyword_usage(text, main_keyword, secondary_keywords)
    lsi = _lsi_coverage_score(text, lsi_keywords or [])
    st = calc_structure(text)
    rd = calc_readability(text)

    actual_words = _count_words(text)
    sentences    = _split_sentences(text)
    total_sent   = len(sentences) or 1
    long_sent    = sum(1 for s in sentences if _count_words(s) > 20)
    short_sent   = sum(1 for s in sentences if _count_words(s) < 8)

    details = {
        "actual_words":       actual_words,
        "target_words":       target_words,
        "word_deviation_pct": round(abs(actual_words - target_words) / max(target_words, 1) * 100, 1),
        "completeness_map":   completeness_details(text, required_elements),
        "sentences_total":    total_sent,
        "sentences_long_pct": round(long_sent  / total_sent * 100, 1),
        "sentences_short_pct":round(short_sent / total_sent * 100, 1),
        "h2_count":           len(re.findall(r'^##\s+\S', text, re.MULTILINE)),
        "h3_count":           len(re.findall(r'^###\s+\S', text, re.MULTILINE)),
    }

    return CodeMetrics(
        length_control = lc,
        completeness   = cp,
        keyword_usage  = ku,
        lsi_coverage   = lsi,
        structure      = st,
        readability    = rd,
        details        = details,
    )
