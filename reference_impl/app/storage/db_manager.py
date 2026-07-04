"""
PostgreSQL: подключение и инициализация таблиц.
Использует psycopg2 с пулом соединений через SimpleConnectionPool.
Заменяет sqlite_manager.py — интерфейс тот же, внутренности другие.
"""
import logging
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_pool: pool.SimpleConnectionPool | None = None


def _get_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise EnvironmentError(
            "DATABASE_URL не задан в .env\n"
            "Пример: DATABASE_URL=postgresql://user:pass@localhost:5432/seo_pipeline"
        )
    return dsn


def init_db() -> None:
    """Инициализирует пул соединений и создаёт таблицы если не существуют."""
    global _pool
    dsn = _get_dsn()
    _pool = pool.SimpleConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    logger.info("PostgreSQL пул создан")
    _create_tables()


def get_connection() -> psycopg2.extensions.connection:
    """Берёт соединение из пула."""
    if _pool is None:
        raise RuntimeError("БД не инициализирована. Вызови init_db() при старте.")
    return _pool.getconn()


def release_connection(conn) -> None:
    """Возвращает соединение в пул."""
    if _pool:
        _pool.putconn(conn)


def close_all() -> None:
    """Закрывает все соединения пула (при выходе из приложения)."""
    if _pool:
        _pool.closeall()
        logger.info("PostgreSQL пул закрыт")


def _create_tables() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS niches (
                    niche_id     TEXT PRIMARY KEY,
                    name_ru      TEXT NOT NULL,
                    description  TEXT
                );

                CREATE TABLE IF NOT EXISTS archetypes (
                    archetype_id     TEXT PRIMARY KEY,
                    niche_id         TEXT NOT NULL REFERENCES niches(niche_id),
                    name_ru          TEXT NOT NULL,
                    description      TEXT,
                    intent_triggers  TEXT[]
                );

                CREATE TABLE IF NOT EXISTS sites (
                    domain      TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    niche_id    TEXT REFERENCES niches(niche_id),
                    is_test     BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS style_references (
                    reference_id          TEXT PRIMARY KEY,
                    name                  TEXT NOT NULL,
                    language              TEXT NOT NULL,
                    geo                   TEXT NOT NULL,
                    niche_tags            TEXT[],
                    notes                 TEXT,
                    extracted_style       TEXT,
                    extracted_tone        TEXT,
                    extracted_age_image   TEXT,
                    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at            TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS authors (
                    author_id    TEXT PRIMARY KEY,
                    site_domain  TEXT NOT NULL REFERENCES sites(domain),
                    name         TEXT NOT NULL,
                    character    TEXT,
                    tone         TEXT,
                    age_image    TEXT,
                    niche_id     TEXT REFERENCES niches(niche_id),
                    reference_id TEXT REFERENCES style_references(reference_id),
                    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS articles (
                    article_id    TEXT PRIMARY KEY,
                    site_domain   TEXT NOT NULL REFERENCES sites(domain),
                    author_id     TEXT REFERENCES authors(author_id),
                    archetype_id  TEXT REFERENCES archetypes(archetype_id),
                    title         TEXT,
                    main_keyword  TEXT,
                    status        TEXT,
                    qa_status     TEXT,
                    qa_score      INTEGER,
                    cost_usd      NUMERIC(10,6) DEFAULT 0,
                    created_at    TEXT,
                    updated_at    TEXT
                );

                CREATE TABLE IF NOT EXISTS pipeline_steps (
                    id            SERIAL PRIMARY KEY,
                    article_id    TEXT,
                    step_name     TEXT,
                    status        TEXT,
                    started_at    TEXT,
                    finished_at   TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS sections (
                    id          SERIAL PRIMARY KEY,
                    article_id  TEXT,
                    section_id  TEXT,
                    status      TEXT,
                    iterations  INTEGER DEFAULT 0,
                    word_count  INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS archetype_picks (
                    id                      SERIAL PRIMARY KEY,
                    article_id              TEXT REFERENCES articles(article_id),
                    suggested_archetype_id  TEXT REFERENCES archetypes(archetype_id),
                    chosen_archetype_id     TEXT REFERENCES archetypes(archetype_id),
                    matched                 BOOLEAN NOT NULL,
                    niche_id                TEXT REFERENCES niches(niche_id),
                    intent                  TEXT,
                    created_at              TEXT NOT NULL
                );
            """)
        conn.commit()

        # Гарантируем существование тестового сайта example.net.
        # Все тестовые/экспериментальные прогоны привязываются к нему;
        # аналитика по умолчанию его отфильтровывает (is_test=true).
        from app.utils.time_utils import now_iso

        # Справочник ниш (7 ниш из ТЗ, раздел 5.4).
        # Заполняется один раз при первой инициализации БД.
        starter_niches = [
            ("travel",         "Трэвел / путешествия",
             "Поездки, маршруты, направления, путеводители."),
            ("home",           "Дом / ремонт / быт",
             "Ремонт, материалы, обустройство, бытовые задачи."),
            ("auto",           "Авто-эксплуатация",
             "Обслуживание, ремонт, выбор, эксплуатационные вопросы."),
            ("lifestyle",      "ЗОЖ / lifestyle",
             "Здоровье, привычки, питание, физическая активность."),
            ("pets",           "Питомцы",
             "Уход, выбор, дрессировка, здоровье животных."),
            ("garden",         "Сад / дача",
             "Растения, посадка, уход, сезонные работы."),
            ("utility",        "Образовательный utilitarian-контент",
             "Инструкции к сервисам, программам, практические how-to."),
        ]
        with conn.cursor() as cur:
            for niche_id, name_ru, description in starter_niches:
                cur.execute("""
                    INSERT INTO niches (niche_id, name_ru, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (niche_id) DO NOTHING
                """, (niche_id, name_ru, description))
        conn.commit()

        # Реестр архетипов по нишам (раздел 5.4 ТЗ).
        # intent_triggers — для будущего автоподбора по интенту запроса.
        starter_archetypes = [
            # Travel
            ("travel-destination-guide",  "travel", "Путеводитель по направлению",
             "Как добраться, когда ехать, что смотреть, бюджет.",
             ["informational"]),
            ("travel-route",              "travel", "Маршрут",
             "Готовый план поездки на N дней.",
             ["informational", "how_to"]),
            ("travel-top-list",           "travel", "Топ / подборка",
             "Лучшие места, что посмотреть в X.",
             ["informational"]),
            ("travel-comparison",         "travel", "Сравнение направлений",
             "X или Y, куда поехать.",
             ["informational"]),
            ("travel-personal",           "travel", "Личный опыт",
             "Как я съездил в X, впечатления и наблюдения.",
             ["informational"]),
            ("travel-practical-guide",    "travel", "Практический гайд",
             "Как оформить, как спланировать, что подготовить.",
             ["how_to"]),

            # Home
            ("home-full-guide",           "home",   "Полное руководство",
             "Всё о X в контексте дома и ремонта.",
             ["informational"]),
            ("home-comparison",           "home",   "Сравнение материалов / решений",
             "X vs Y: цена, срок, плюсы и минусы.",
             ["informational"]),
            ("home-howto-diy",            "home",   "Пошаговая инструкция (DIY)",
             "Как сделать X своими руками.",
             ["how_to"]),
            ("home-top-choice",           "home",   "Топ / выбор",
             "Лучшие X для дома, как выбрать X.",
             ["informational"]),
            ("home-problem-solving",      "home",   "Решение проблемы",
             "Как устранить X, что делать если X.",
             ["how_to", "informational"]),

            # Auto
            ("auto-howto-service",        "auto",   "Как сделать / обслужить",
             "Пошаговое обслуживание или ремонт.",
             ["how_to"]),
            ("auto-comparison",           "auto",   "Сравнение",
             "X vs Y.",
             ["informational"]),
            ("auto-top-choice",           "auto",   "Выбор / топ",
             "Как выбрать X, лучшие X.",
             ["informational"]),
            ("auto-problem-solving",      "auto",   "Решение проблемы",
             "Что делать если X.",
             ["how_to", "informational"]),
            ("auto-full-guide",           "auto",   "Полное руководство",
             "Всё про X в контексте эксплуатации.",
             ["informational"]),

            # Lifestyle
            ("lifestyle-full-guide",      "lifestyle", "Полное руководство",
             "Всё о X для здоровья и образа жизни.",
             ["informational"]),
            ("lifestyle-howto",           "lifestyle", "How-To",
             "Как начать X, как делать X.",
             ["how_to"]),
            ("lifestyle-top-list",        "lifestyle", "Топ / подборка",
             "Лучшие X.",
             ["informational"]),
            ("lifestyle-myths",           "lifestyle", "Мифы и факты",
             "Правда о X, развенчание мифов.",
             ["informational"]),
            ("lifestyle-comparison",      "lifestyle", "Сравнение подходов",
             "X vs Y, какой подход выбрать.",
             ["informational"]),

            # Pets
            ("pets-full-guide",           "pets",   "Полное руководство",
             "Всё об уходе за X.",
             ["informational"]),
            ("pets-howto",                "pets",   "How-To",
             "Как приучить / лечить / кормить.",
             ["how_to"]),
            ("pets-choice",               "pets",   "Выбор",
             "Как выбрать X, породы, корма.",
             ["informational"]),
            ("pets-problem-solving",      "pets",   "Решение проблемы",
             "Что делать если питомец X.",
             ["how_to", "informational"]),
            ("pets-comparison",           "pets",   "Сравнение",
             "X vs Y.",
             ["informational"]),

            # Garden
            ("garden-full-guide",         "garden", "Полное руководство",
             "Всё о выращивании X.",
             ["informational"]),
            ("garden-howto",              "garden", "Пошаговая инструкция",
             "Как посадить, ухаживать.",
             ["how_to"]),
            ("garden-seasonal",           "garden", "Сезонный гайд",
             "Что делать в саду в X сезон.",
             ["informational", "how_to"]),
            ("garden-top-choice",         "garden", "Выбор / топ",
             "Лучшие сорта, инструменты.",
             ["informational"]),
            ("garden-problem-solving",    "garden", "Решение проблемы",
             "Болезни, вредители.",
             ["how_to", "informational"]),

            # Utility
            ("utility-service-guide",     "utility", "Инструкция к сервису",
             "Как пользоваться X.",
             ["how_to"]),
            ("utility-howto",             "utility", "How-To",
             "Как сделать X в сервисе или программе.",
             ["how_to"]),
            ("utility-comparison",        "utility", "Сравнение сервисов",
             "X vs Y.",
             ["informational"]),
            ("utility-problem-solving",   "utility", "Решение проблемы",
             "Как исправить ошибку X.",
             ["how_to"]),
            ("utility-full-guide",        "utility", "Полное руководство",
             "Всё о X в контексте сервиса.",
             ["informational"]),
        ]
        with conn.cursor() as cur:
            for archetype_id, niche_id, name_ru, description, triggers in starter_archetypes:
                cur.execute("""
                    INSERT INTO archetypes (archetype_id, niche_id, name_ru,
                                            description, intent_triggers)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (archetype_id) DO NOTHING
                """, (archetype_id, niche_id, name_ru, description, triggers))
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sites (domain, name, niche_id, is_test, created_at)
                VALUES ('example.net', 'Тестовый сайт', NULL, TRUE, %s)
                ON CONFLICT (domain) DO NOTHING
            """, (now_iso(),))
        conn.commit()

        # Стартовый каталог писателей-референсов для русского языка.
        # При создании автора через UI можно выбрать одного из них —
        # агент style_extractor извлечёт стилистические маркеры в поле
        # character этого автора. Имя писателя в финальный промпт Writer'а
        # не попадает: автор работает уже с извлечёнными признаками стиля.
        starter_references = [
            ("dovlatov_sergey",   "Сергей Довлатов",  "ru", "RU",
             ["travel","lifestyle","pets","utility","home","auto","garden"],
             "Короткие предложения, ирония, конкретные детали быта."),
            ("veller_mikhail",    "Михаил Веллер",    "ru", "RU",
             ["lifestyle","utility","home","auto"],
             "Плотная мысль, афористичность, уверенный тон."),
            ("parfyonov_leonid",  "Леонид Парфёнов",  "ru", "RU",
             ["travel","lifestyle","utility"],
             "Журналистская плотность, факты, ёмкие формулировки."),
            ("dud_yury",          "Юрий Дудь",        "ru", "RU",
             ["lifestyle","utility","travel"],
             "Прямота, разговорный язык, въедливые вопросы."),
            ("kolesnikov_andrey", "Андрей Колесников","ru", "RU",
             ["utility","lifestyle"],
             "Сухая ирония, наблюдательность, деловой язык."),
            ("kashin_oleg",       "Олег Кашин",       "ru", "RU",
             ["lifestyle","utility"],
             "Резкость, личная позиция, сложный синтаксис."),
            ("kaganov_leonid",    "Леонид Каганов",   "ru", "RU",
             ["utility","lifestyle","home"],
             "Лёгкая ирония, бытовой язык, простые объяснения."),
            ("lebedev_artemy",    "Артемий Лебедев",  "ru", "RU",
             ["travel","home","lifestyle","auto","utility"],
             "Резкие суждения, личный взгляд, минимум воды."),
            ("varlamov_ilya",     "Илья Варламов",    "ru", "RU",
             ["travel","home"],
             "Плотные обзоры, фактура, сравнения, наблюдения."),
            ("pivovarov_alexey",  "Алексей Пивоваров","ru", "RU",
             ["utility","lifestyle","travel"],
             "Расследовательский стиль, нейтральный тон, опора на источники."),
            ("bykov_dmitry",      "Дмитрий Быков",    "ru", "RU",
             ["lifestyle"],
             "Литературность, длинные периоды, культурные отсылки."),
            ("rubina_dina",       "Дина Рубина",      "ru", "RU",
             ["lifestyle","pets","home"],
             "Тёплая проза, образы, личные интонации."),
        ]
        with conn.cursor() as cur:
            for ref_id, name, language, geo, tags, notes in starter_references:
                cur.execute("""
                    INSERT INTO style_references
                        (reference_id, name, language, geo, niche_tags, notes, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
                    ON CONFLICT (reference_id) DO NOTHING
                """, (ref_id, name, language, geo, tags, notes, now_iso()))
        conn.commit()

        # Стартовые профили авторов для тестового сайта.
        # На старте — 2 контрастных характера, чтобы было на чём проверять
        # ось «автор»: один аналитический, второй эмоционально-вовлечённый.
        # Богатую библиотеку добавляем позже, когда подтвердим базовый текст.
        # Идентификаторы фиксированные — чтобы повторный запуск не плодил дублей.
        starter_authors = [
            (
                "test-author-pragmatic-01", "example.net",
                "Андрей Соколов",
                "Прагматичный обозреватель средних лет. Опирается на факты "
                "и сравнения, скептичен к маркетинговым обещаниям, любит "
                "конкретные цифры и собственные оговорки. Не боится сказать "
                "«мне это не подошло» и объяснить почему.",
                "сдержанный, аналитический, с лёгкой иронией",
                "около 40 лет",
            ),
            (
                "test-author-enthusiastic-01", "example.net",
                "Мария Лебедева",
                "Молодой увлечённый автор, пишет с живой интонацией и "
                "личными наблюдениями. Делится впечатлениями, не боится "
                "эмоций, добавляет бытовые детали. Текст читается как "
                "рассказ другу, а не как справка.",
                "тёплый, разговорный, открытый",
                "около 27 лет",
            ),
        ]
        with conn.cursor() as cur:
            for author_id, site_domain, name, character, tone, age_image in starter_authors:
                cur.execute("""
                    INSERT INTO authors (author_id, site_domain, name, character,
                                         tone, age_image, niche_id, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, TRUE, %s)
                    ON CONFLICT (author_id) DO NOTHING
                """, (author_id, site_domain, name, character, tone, age_image, now_iso()))
        conn.commit()

        logger.info("Таблицы PostgreSQL готовы")
    finally:
        release_connection(conn)
