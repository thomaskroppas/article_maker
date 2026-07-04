"""
Image-finder: ищет картинки для статьи и вставляет в markdown.

Логика:
  1. Парсим markdown, находим точки вставки:
     - Плейсхолдеры Writer'а (блоки «Редактору: ...») — обязательные.
     - После H2/H3 если до следующего заголовка ≥150 слов
       И с последней картинки прошло ≥400 слов.
  2. Для каждой точки формируем поисковый запрос (заголовок + контекст).
  3. По очереди опрашиваем провайдеры на родном языке статьи.
  4. Для тех точек где ничего не нашли — один батчевый LLM-вызов переводит
     запрос на английский, повторяем поиск.
  5. Вставляем markdown с картинкой и подписью-ссылкой.
"""
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Dict

from app.services.image_finder import get_providers, ImageResult
from app.services import translation_cache

logger = logging.getLogger(__name__)


# Регэксп под плейсхолдеры Writer'а.
# Он у нас пишет их в нескольких форматах:
#   [Редактору: ...]
#   > 📍 *Редактору: ...*
#   > **Редактору:** ...
_PLACEHOLDER_RE = re.compile(
    r"(?:^>\s*[^\n]*[Рр]едактору[^\n]*\n?)|(?:\[[Рр]едактору:[^\]]+\])",
    re.MULTILINE,
)

# Все заголовки H2/H3
_HEADING_RE = re.compile(r"^(##{1,2})\s+(.+)$", re.MULTILINE)


@dataclass
class InsertPoint:
    position:    int      # позиция в исходном markdown (символ)
    kind:        str      # "placeholder" | "after_heading"
    placeholder: Optional[str]  # сам текст плейсхолдера если kind=placeholder
    query:       str      # поисковый запрос на языке статьи
    context:     str      # дополнительный контекст для возможного перевода


def _count_words(text: str) -> int:
    return len(re.findall(r"\b[\wа-яёА-ЯЁ]+\b", text, re.UNICODE))


def _clean_query(text: str) -> str:
    """Чистит текст для поискового запроса: убирает эмодзи и пунктуацию."""
    # Убираем эмодзи (символы вне базовых букв/цифр/пробелов/тире)
    text = re.sub(r"[^\w\s\-а-яА-ЯёЁ]", " ", text, flags=re.UNICODE)
    # Схлопываем лишние пробелы
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_query(main_topic: str, section_title: str) -> str:
    """
    Формирует поисковый запрос из главной темы и заголовка секции.
    Главная тема обрезается до первых 4-5 слов, чтобы не было простыни.
    """
    topic_words = _clean_query(main_topic).split()
    topic_short = " ".join(topic_words[:4])  # «Озеро Байкал где находится»
    title_clean = _clean_query(section_title)
    return f"{topic_short} {title_clean}".strip()


def _find_placeholders(markdown: str, main_topic: str) -> List[InsertPoint]:
    """Находит плейсхолдеры от Writer'а — обязательные точки вставки."""
    points = []
    for m in _PLACEHOLDER_RE.finditer(markdown):
        # Берём заголовок предыдущей секции как контекст
        section_title = _find_section_title_before(markdown, m.start())
        query = _build_query(main_topic, section_title)
        points.append(InsertPoint(
            position=m.start(),
            kind="placeholder",
            placeholder=m.group(0),
            query=query,
            context=section_title,
        ))
    return points


def _find_section_title_before(markdown: str, pos: int) -> str:
    """Берёт текст последнего заголовка до позиции pos."""
    last = ""
    for m in _HEADING_RE.finditer(markdown):
        if m.start() > pos:
            break
        last = m.group(2).strip()
    return last


def _find_extra_points(markdown: str, main_topic: str,
                       existing_positions: List[int],
                       interval_words: int = 250,
                       min_section_words: int = 60) -> List[InsertPoint]:
    """
    Дополнительные точки — сразу после H2/H3.
    Условия:
      - между заголовком и следующим заголовком ≥ min_section_words слов;
      - с последней картинки прошло ≥ interval_words слов.
    """
    points = []
    headings = list(_HEADING_RE.finditer(markdown))
    if not headings:
        return points

    # Позиция последней «картинки» — для подсчёта интервала.
    # Начинаем с 0 (начало текста), движемся вперёд по статье.
    last_image_pos = 0
    sorted_existing = sorted(existing_positions)

    _EXCLUDED_TITLES = (
        "источник", "sources", "references",
        "faq", "часто задаваемые", "frequently asked",
        "заключение", "выводы", "conclusion", "итог",
    )

    for i, h in enumerate(headings):
        # Исключаем «технические» секции — для них картинка не нужна
        title_lc = h.group(2).strip().lower()
        if any(excl in title_lc for excl in _EXCLUDED_TITLES):
            continue

        # Конец секции = начало следующего заголовка (или конец текста)
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        section_text = markdown[h.end():end]
        section_words = _count_words(section_text)
        if section_words < min_section_words:
            continue

        # Обновляем last_image_pos если плейсхолдеры прошли до этого заголовка
        for pos in sorted_existing:
            if pos < h.start() and pos > last_image_pos:
                last_image_pos = pos

        # Сколько слов между last_image_pos и нашим заголовком
        words_since_last = _count_words(markdown[last_image_pos:h.start()])
        if words_since_last < interval_words:
            continue

        # Вставляем после заголовка и пустой строки (или сразу за \n)
        insert_pos = h.end()
        # Пропускаем перевод строки если есть
        if insert_pos < len(markdown) and markdown[insert_pos] == "\n":
            insert_pos += 1

        title = h.group(2).strip()
        query = _build_query(main_topic, title)
        points.append(InsertPoint(
            position=insert_pos,
            kind="after_heading",
            placeholder=None,
            query=query,
            context=title,
        ))
        last_image_pos = insert_pos

    return points


def _format_image_block(img: ImageResult, alt: str) -> str:
    """Формирует markdown-блок картинки с подписью-ссылкой."""
    return (
        f"\n![{alt}]({img.url})\n"
        f"*[Источник]({img.source_url}) — {img.attribution}*\n\n"
    )


class ImageFinderAgent:
    """
    Сам агент. Принимает markdown, возвращает обновлённый markdown с картинками.
    """
    agent_name = "image_finder_agent"

    def __init__(self, llm_client=None):
        # LLM используется только для batch-перевода запросов на английский.
        self._llm = llm_client
        self._providers = get_providers()

    def run(self,
            markdown: str,
            main_topic: str,
            main_keyword: str,
            article_dir,
            language: str = "ru") -> str:
        """
        Точка входа. Возвращает markdown с вставленными картинками.
        article_dir — папка статьи, куда сохраняем картинки в подпапку images/.
        Если что-то не вышло — возвращает оригинальный markdown без падений.
        """
        try:
            return self._run(markdown, main_topic, main_keyword, article_dir, language)
        except Exception as e:
            logger.warning(f"[image_finder] упал: {e} — возвращаем без картинок")
            return markdown

    # ─── Внутренности ─────────────────────────────────────────────────────────

    def _run(self, markdown: str, main_topic: str,
             main_keyword: str, article_dir, language: str) -> str:
        # Шаг 1: точки вставки
        placeholders = _find_placeholders(markdown, main_topic)
        existing_positions = [p.position for p in placeholders]
        extras = _find_extra_points(markdown, main_topic, existing_positions)

        points = placeholders + extras
        points.sort(key=lambda p: p.position)

        if not points:
            logger.info("[image_finder] точек вставки не найдено")
            return markdown
        logger.info(
            f"[image_finder] точек: {len(points)} "
            f"(плейсхолдеров={len(placeholders)}, доп={len(extras)})"
        )

        # Шаг 2: получаем список ключей от LLM (или из кэша).
        # Один ключ — один поисковый запрос. Идём по списку по очереди.
        image_keys = self._generate_image_keys(main_keyword, main_topic)
        logger.info(f"[image_finder] ключи: {image_keys}")

        # Шаг 3: для каждой точки ищем по своему ключу.
        # Ключи уже на английском (от LLM), поиск в провайдерах тоже на en —
        # это даёт лучшую релевантность в стоковых базах. Шаг fallback-перевода
        # больше не нужен.
        used_urls: set[str] = set()
        results: Dict[int, Optional[ImageResult]] = {}
        for i, p in enumerate(points):
            key = image_keys[i % len(image_keys)] if image_keys else main_keyword
            r = self._search_in_providers(key, "en", used_urls)
            results[p.position] = r
            if r:
                used_urls.add(r.url)

        # Шаг 4: вставляем картинки в markdown
        return self._apply_results(markdown, points, results, article_dir)

    def _search_in_providers(self, query: str, language: str,
                             used_urls: set[str]) -> Optional[ImageResult]:
        """
        Идёт по провайдерам по очереди, возвращает первую картинку,
        чей URL ещё не использован в этой статье.
        """
        for provider in self._providers:
            if not provider.is_available():
                logger.info(f"[image_finder] {provider.name}: пропуск (нет ключей)")
                continue
            results = provider.search_many(query, language=language, limit=5)
            if not results:
                logger.info(f"[image_finder] {provider.name}: 0 результатов "
                            f"по '{query}' (lang={language})")
                continue
            logger.info(f"[image_finder] {provider.name}: {len(results)} результатов "
                        f"по '{query}' (lang={language})")
            for r in results:
                if r.url in used_urls:
                    logger.info(f"[image_finder] {provider.name}: пропуск дубля")
                    continue
                logger.info(f"[image_finder] {provider.name} ВЗЯТО: {r.url[:80]}")
                return r
        return None

    def _generate_image_keys(self, main_keyword: str,
                             article_title: str) -> List[str]:
        """
        Генерирует 10 коротких ключей для поиска картинок. Использует кэш
        по main_keyword: повторные статьи с тем же ключом — без LLM.
        При ошибке LLM — возвращает [main_keyword] как fallback.
        """
        from app.services import image_keys_cache
        cached = image_keys_cache.get(main_keyword)
        if cached:
            logger.info(f"[image_finder] ключи взяты из кэша ({len(cached)})")
            return cached

        if not self._llm:
            return [main_keyword]

        prompt = (
            f"Тема статьи: «{article_title}»\n"
            f"Подбери для нее 10 одно-двух сложных ключей на АНГЛИЙСКОМ ЯЗЫКЕ "
            f"для поиска картинок в стоковых базах (Unsplash, Pixabay). "
            f"Ключи должны полностью описывать тему, дополнять статью и не дублироваться.\n"
            f"Пример:\n"
            f"Тема статьи: «Озеро Байкал где находится 🌊 Глубина, координаты и факты»\n"
            f"Ключи: lake baikal, baikal winter, baikal summer, baikal olkhon, "
            f"baikal seal, baikal nature, baikal map, baikal ice, "
            f"baikal coast, baikal russia\n\n"
            f"Верни ТОЛЬКО JSON-массив строк без комментариев: "
            f'["key1", "key2", ...]'
        )
        try:
            resp = self._llm.call(
                agent_name="image_keys_agent",
                prompt=prompt,
            )
            from app.services.json_parser import extract_json
            parsed = extract_json(resp.text)
            if isinstance(parsed, list) and parsed:
                keys = [str(k).strip() for k in parsed if str(k).strip()]
                if keys:
                    image_keys_cache.put(main_keyword, keys)
                    logger.info(f"[image_finder] LLM сгенерировал {len(keys)} ключей")
                    return keys
        except Exception as e:
            logger.warning(f"[image_finder] генерация ключей упала: {e}")

        return [main_keyword]

    def _translate_batch(self, queries: List[str]) -> Dict[str, str]:
        """
        Переводит список запросов на английский одним LLM-вызовом.
        Использует кеш в data/translation_cache.json — повторно не переводит.
        """
        # Что уже в кеше
        result: Dict[str, str] = {}
        need_translate = []
        for q in queries:
            cached = translation_cache.get(q)
            if cached:
                result[q] = cached
            else:
                need_translate.append(q)

        if not need_translate:
            return result

        # Один LLM-вызов на батч
        prompt = (
            "Переведи следующие поисковые запросы для поиска картинок на английский. "
            "Сохрани краткость и ключевые слова, не добавляй ничего лишнего. "
            "Верни ТОЛЬКО JSON-объект {оригинал: перевод} без комментариев.\n\n"
            "Запросы:\n" + "\n".join(f"- {q}" for q in need_translate)
        )
        try:
            resp = self._llm.call(
                agent_name="image_keys_agent",
                prompt=prompt,
            )
            from app.services.json_parser import extract_json
            parsed = extract_json(resp.text) or {}
            if isinstance(parsed, dict):
                for q in need_translate:
                    if q in parsed and isinstance(parsed[q], str):
                        result[q] = parsed[q]
                # Сохраняем в кеш
                translation_cache.put_many({q: result[q] for q in need_translate if q in result})
        except Exception as e:
            logger.warning(f"[image_finder] LLM-перевод упал: {e}")

        return result

    def _apply_results(self, markdown: str,
                       points: List[InsertPoint],
                       results: Dict[int, Optional[ImageResult]],
                       article_dir) -> str:
        """
        Скачивает картинки, конвертирует в WebP с обрезкой 16:9, сохраняет
        в article_dir/images/N.webp и вставляет в markdown относительные ссылки.
        Подпись «Источник» по-прежнему ведёт на оригинальный URL источника.

        Идём с конца, чтобы позиции не сбивались.
        """
        from pathlib import Path
        from app.services.image_processor import fetch_and_compress

        article_dir = Path(article_dir)
        images_dir = article_dir / "images"

        # Нумерация локальных файлов: 1.webp, 2.webp, ... в порядке появления
        # (а не позиции). Поэтому сначала формируем порядок по position возр.
        ordered = [p for p in sorted(points, key=lambda x: x.position) if results.get(p.position)]
        local_paths: Dict[int, str] = {}  # position -> "images/N.webp"
        for i, p in enumerate(ordered, start=1):
            img = results[p.position]
            out_path = images_dir / f"{i}.webp"
            saved = fetch_and_compress(img.url, out_path)
            if saved is None:
                logger.warning(f"[image_finder] не удалось обработать {img.url[:80]}")
                continue
            local_paths[p.position] = f"images/{out_path.name}"

        # Теперь идём в обратном порядке и вставляем в markdown
        out = markdown
        for p in sorted(points, key=lambda x: x.position, reverse=True):
            img = results.get(p.position)
            local_path = local_paths.get(p.position)
            if not img or not local_path:
                continue

            alt = p.context or "Изображение"
            # Локальный путь — для <img src>; source_url — для подписи
            block = (
                f"\n![{alt}]({local_path})\n"
                f"*[Источник]({img.source_url}) — {img.attribution}*\n\n"
            )

            if p.kind == "placeholder" and p.placeholder:
                out = out.replace(p.placeholder, block.strip(), 1)
            else:
                out = out[:p.position] + block + out[p.position:]
        return out
