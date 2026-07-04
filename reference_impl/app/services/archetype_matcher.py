"""
Автоподбор архетипа статьи на основе правил.
Без LLM: смотрит на ключевые слова в теме + интент + нишу.

Используется на этапе подготовки outline: предлагает архетип, пользователь
подтверждает или меняет, результат логируется в archetype_picks для
последующего анализа точности.
"""
from typing import Optional, Dict, List, Tuple
import re

from app.storage.repositories import get_archetypes_for_niche


# Ключевые маркеры архетипов в теме статьи.
# Регэкспы по нижнему регистру. Победитель — архетип с наибольшим числом
# совпадений. При равенстве побеждает первый в списке отфильтрованных по интенту.
#
# Карта общая для всех ниш: маркеры срабатывают, только если архетип в принципе
# есть у ниши (фильтр по niche_id) и подходит по интенту.
ARCHETYPE_MARKERS: Dict[str, List[str]] = {
    # ── Сравнения ─────────────────────────────────────────────────────────────
    "travel-comparison":      [r"\bили\b", r"\bvs\b", r"\bпротив\b", r"\bсравнен", r"\bчто лучше", r"\bкуда лучше"],
    "home-comparison":        [r"\bили\b", r"\bvs\b", r"\bпротив\b", r"\bсравнен", r"\bчто лучше", r"\bотличи"],
    "auto-comparison":        [r"\bили\b", r"\bvs\b", r"\bпротив\b", r"\bсравнен", r"\bчто лучше", r"\bотличи"],
    "lifestyle-comparison":   [r"\bили\b", r"\bvs\b", r"\bпротив\b", r"\bсравнен", r"\bотличи"],
    "pets-comparison":        [r"\bили\b", r"\bvs\b", r"\bпротив\b", r"\bсравнен", r"\bотличи"],
    "utility-comparison":     [r"\bили\b", r"\bvs\b", r"\bпротив\b", r"\bсравнен", r"\bотличи", r"\bальтернатив"],

    # ── Топы / подборки / выбор ───────────────────────────────────────────────
    "travel-top-list":        [r"\bтоп\b", r"\bтоп-", r"\bлучш", r"\bподборк", r"\bрейтинг",
                               r"\bдостопримечательност", r"\bчто посмотреть", r"\bкуда сходить",
                               r"\bкуда поехать", r"\bинтересные мест"],
    "home-top-choice":        [r"\bтоп\b", r"\bтоп-", r"\bлучш", r"\bкак выбрать", r"\bвыбор",
                               r"\bкакой\b", r"\bкакую\b", r"\bкакое\b", r"\bкакие\b"],
    "auto-top-choice":        [r"\bтоп\b", r"\bтоп-", r"\bлучш", r"\bкак выбрать", r"\bвыбор",
                               r"\bкакой\b", r"\bкакую\b", r"\bкакое\b"],
    "lifestyle-top-list":     [r"\bтоп\b", r"\bтоп-", r"\bлучш", r"\bподборк", r"\bрейтинг"],
    "pets-choice":            [r"\bкак выбрать", r"\bвыбор", r"\bпорода", r"\bкорм", r"\bкакой\b",
                               r"\bкакую\b", r"\bкакое\b"],
    "garden-top-choice":      [r"\bтоп\b", r"\bтоп-", r"\bлучш", r"\bсорт", r"\bинструмент", r"\bвыбор"],

    # ── How-To / инструкции ───────────────────────────────────────────────────
    "travel-practical-guide": [r"\bкак ", r"\bинструкци", r"\bоформи", r"\bподготови",
                               r"\bспланиров", r"\bзабронир", r"\bкуда обратиться"],
    "home-howto-diy":         [r"\bкак ", r"\bсвоими руками", r"\bинструкци", r"\bпошагов",
                               r"\bсамостоятельно", r"\bсдела", r"\bремонт\b", r"\bустанов",
                               r"\bнастро", r"\bпокле", r"\bпокрас"],
    "auto-howto-service":     [r"\bкак ", r"\bобслуж", r"\bпошагов", r"\bзамени", r"\bпроверить",
                               r"\bремонт\b", r"\bтехобслужив"],
    "lifestyle-howto":        [r"\bкак ", r"\bинструкци", r"\bпошагов", r"\bначать\b", r"\bначни"],
    "pets-howto":             [r"\bкак ", r"\bприучи", r"\bкорми", r"\bлечи", r"\bдресс", r"\bобучи"],
    "garden-howto":           [r"\bкак ", r"\bпосад", r"\bухаж", r"\bвыращ", r"\bудобр", r"\bподкорм",
                               r"\bобрезк", r"\bполив"],
    "utility-service-guide":  [r"\bкак пользоваться", r"\bинструкци", r"\bгид по", r"\bобучен"],
    "utility-howto":          [r"\bкак ", r"\bпошагов", r"\bсдела", r"\bнастро", r"\bустанов"],

    # ── Решение проблем ───────────────────────────────────────────────────────
    "home-problem-solving":   [r"\bчто делать", r"\bпробле", r"\bустран", r"\bпочему", r"\bне работает",
                               r"\bтечёт", r"\bтечет", r"\bсломал", r"\bне включ", r"\bне греет"],
    "auto-problem-solving":   [r"\bчто делать", r"\bпробле", r"\bпочему", r"\bне работает",
                               r"\bне заводит", r"\bстук", r"\bошибк", r"\bдым", r"\bтечь"],
    "pets-problem-solving":   [r"\bчто делать", r"\bпробле", r"\bпочему", r"\bне ест", r"\bбоит",
                               r"\bотказыва", r"\bкуса", r"\bаллерги"],
    "garden-problem-solving": [r"\bболезн", r"\bвредител", r"\bпробле", r"\bпочему", r"\bжелте",
                               r"\bсохн", r"\bгни", r"\bне цвет"],
    "utility-problem-solving":[r"\bошибк", r"\bне работает", r"\bпочему", r"\bпробле",
                               r"\bне открыва", r"\bне грузит", r"\bне сохран"],

    # ── Специальные: путеводители, маршруты, сезонные, мифы, личный опыт ──────
    # destination-guide ловит «гайды по месту/объекту» — основной informational
    # для travel при отсутствии явных маркеров других архетипов.
    "travel-destination-guide":[r"\bпутеводитель", r"\bпоездк", r"\bв город", r"\bв страну",
                                r"\bгде находится", r"\bгде это\b", r"\bкоординаты",
                                r"\bглубина", r"\bвысота\b", r"\bдлина\b", r"\bплощадь\b",
                                r"\bистория\b", r"\bфакты о\b", r"\bинтересные факты",
                                r"\bприрода\b", r"\bклимат\b", r"\bпогода\b",
                                r"\bозеро\b", r"\bгора\b", r"\bвулкан\b", r"\bводопад\b",
                                r"\bрека\b", r"\bморе\b", r"\bпарк\b", r"\bзаповедник\b",
                                r"\bостров\b", r"\bперевал\b", r"\bущел"],
    "travel-route":           [r"\bмаршрут", r"\bна .* дн", r"\bпрогра", r"\bпрограмма поездк"],
    "travel-personal":        [r"\bкак я ", r"\bопыт", r"\bвпечатлен", r"\bдневник",
                               r"\bпоехал", r"\bпосетил", r"\bотзыв"],
    "garden-seasonal":        [r"\bвесн", r"\bлет", r"\bосен", r"\bзим", r"\bсезон",
                               r"\bв феврале", r"\bв марте", r"\bв апреле", r"\bв мае",
                               r"\bв июне", r"\bв июле", r"\bв августе", r"\bв сентябре",
                               r"\bв октябре"],
    "lifestyle-myths":        [r"\bмиф", r"\bправда", r"\bна самом деле", r"\bразвенч"],

    # ── «Полные руководства» — fallback для informational ─────────────────────
    "travel-full-guide":      [r"\bвс[её] о\b", r"\bполное руководство", r"\bгайд\b"],
    "home-full-guide":        [r"\bвс[её] о\b", r"\bполное руководство", r"\bгайд\b"],
    "auto-full-guide":        [r"\bвс[её] о\b", r"\bполное руководство", r"\bгайд\b"],
    "lifestyle-full-guide":   [r"\bвс[её] о\b", r"\bполное руководство", r"\bгайд\b"],
    "pets-full-guide":        [r"\bвс[её] о\b", r"\bуход\b", r"\bсодержан"],
    "garden-full-guide":      [r"\bвс[её] о\b", r"\bвыращиван"],
    "utility-full-guide":     [r"\bвс[её] о\b", r"\bполное руководство", r"\bгайд\b", r"\bобзор\b"],
}

# Дефолтный архетип для каждой ниши — используется fallback'ом если
# ни один маркер не сработал. Подбирается под интент: для informational —
# «full-guide» или «destination-guide», для how_to — соответствующий howto.
DEFAULT_ARCHETYPE: Dict[str, Dict[str, str]] = {
    "travel":    {"informational": "travel-destination-guide", "how_to": "travel-practical-guide"},
    "home":      {"informational": "home-full-guide",          "how_to": "home-howto-diy"},
    "auto":      {"informational": "auto-full-guide",          "how_to": "auto-howto-service"},
    "lifestyle": {"informational": "lifestyle-full-guide",     "how_to": "lifestyle-howto"},
    "pets":      {"informational": "pets-full-guide",          "how_to": "pets-howto"},
    "garden":    {"informational": "garden-full-guide",        "how_to": "garden-howto"},
    "utility":   {"informational": "utility-full-guide",       "how_to": "utility-howto"},
}


def suggest_archetype_by_rules(topic: str,
                               niche_id: str,
                               intent: str) -> Optional[str]:
    """
    Подбор архетипа по регэкспам — fallback на случай если LLM недоступна.

    Алгоритм:
      1. Берём архетипы ниши из БД.
      2. Фильтруем по интенту (intent должен быть в intent_triggers архетипа).
      3. Считаем число совпадений ключевых маркеров каждого с темой.
      4. Возвращаем архетип с максимумом совпадений.
      5. Если совпадений нет — возвращаем DEFAULT_ARCHETYPE[niche][intent].
      6. Если дефолт не задан — первый из отфильтрованных. Если нет даже — None.
    """
    archetypes = get_archetypes_for_niche(niche_id)
    if not archetypes:
        return None

    # Фильтр по интенту
    by_intent = [
        a for a in archetypes
        if a.get("intent_triggers") and intent in a["intent_triggers"]
    ]
    if not by_intent:
        return None

    topic_lc = (topic or "").lower()

    # Считаем совпадения маркеров для каждого подходящего архетипа
    scored: List[Tuple[int, str]] = []
    for a in by_intent:
        markers = ARCHETYPE_MARKERS.get(a["archetype_id"], [])
        score = sum(1 for pat in markers if re.search(pat, topic_lc))
        scored.append((score, a["archetype_id"]))

    scored.sort(key=lambda x: -x[0])
    best_score, best_id = scored[0]

    # Если хотя бы один маркер сработал — берём его
    if best_score > 0:
        return best_id

    # Иначе — дефолтный архетип ниши под интент
    default = DEFAULT_ARCHETYPE.get(niche_id, {}).get(intent)
    if default and any(a["archetype_id"] == default for a in by_intent):
        return default

    # Последний рубеж — первый из отфильтрованных
    return best_id


def suggest_archetype(topic: str,
                      niche_id: str,
                      intent: str,
                      llm_client=None) -> Optional[str]:
    """
    Главная функция автоподбора архетипа. Три уровня надёжности:
      1. LLM (Claude Haiku) — первичный путь, понимает контекст.
      2. Регэкспы — fallback если LLM упала.
      3. Дефолт ниши — последний рубеж (внутри suggest_archetype_by_rules).

    llm_client передаётся опционально. Если не передан — сразу регэкспы
    (для unit-тестов и случая «LLM-стек не инициализирован»).
    """
    import logging
    log = logging.getLogger(__name__)

    archetypes = get_archetypes_for_niche(niche_id)
    if not archetypes:
        return None

    # Фильтруем по интенту здесь же — отдадим LLM только релевантные
    by_intent = [
        a for a in archetypes
        if a.get("intent_triggers") and intent in a["intent_triggers"]
    ]
    if not by_intent:
        return None

    # Попытка 1: LLM
    if llm_client is not None:
        try:
            from app.agents.archetype_picker_agent import ArchetypePickerAgent
            agent = ArchetypePickerAgent(llm_client)
            chosen = agent.run(topic=topic, intent=intent, archetypes=by_intent)
            if chosen:
                return chosen
            log.info("[suggest_archetype] LLM не вернула валидный id, fallback на регэкспы")
        except Exception as e:
            log.warning(f"[suggest_archetype] LLM не сработала ({e}), fallback на регэкспы")

    # Попытка 2: регэкспы + дефолт
    return suggest_archetype_by_rules(topic, niche_id, intent)
