"""seed niches + archetypes

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-04

Seed справочников из seed/seed_niches_archetypes.py (7 ниш, 36 архетипов).
Данные встроены в миграцию (self-contained snapshot, не зависит от внешнего файла).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NICHES = [
    ("travel", "Трэвел / путешествия", "Поездки, маршруты, направления, путеводители."),
    ("home", "Дом / ремонт / быт", "Ремонт, материалы, обустройство, бытовые задачи."),
    ("auto", "Авто-эксплуатация", "Обслуживание, ремонт, выбор, эксплуатационные вопросы."),
    ("lifestyle", "ЗОЖ / lifestyle", "Здоровье, привычки, питание, физическая активность."),
    ("pets", "Питомцы", "Уход, выбор, дрессировка, здоровье животных."),
    ("garden", "Сад / дача", "Растения, посадка, уход, сезонные работы."),
    ("utility", "Образовательный utilitarian-контент", "Инструкции к сервисам, программам, практические how-to."),
]

ARCHETYPES = [
    ("travel-destination-guide", "travel", "Путеводитель по направлению", "Как добраться, когда ехать, что смотреть, бюджет.", ["informational"]),
    ("travel-route", "travel", "Маршрут", "Готовый план поездки на N дней.", ["informational", "how_to"]),
    ("travel-top-list", "travel", "Топ / подборка", "Лучшие места, что посмотреть в X.", ["informational"]),
    ("travel-comparison", "travel", "Сравнение направлений", "X или Y, куда поехать.", ["informational"]),
    ("travel-personal", "travel", "Личный опыт", "Как я съездил в X, впечатления и наблюдения.", ["informational"]),
    ("travel-practical-guide", "travel", "Практический гайд", "Как оформить, как спланировать, что подготовить.", ["how_to"]),
    ("home-full-guide", "home", "Полное руководство", "Всё о X в контексте дома и ремонта.", ["informational"]),
    ("home-comparison", "home", "Сравнение материалов / решений", "X vs Y: цена, срок, плюсы и минусы.", ["informational"]),
    ("home-howto-diy", "home", "Пошаговая инструкция (DIY)", "Как сделать X своими руками.", ["how_to"]),
    ("home-top-choice", "home", "Топ / выбор", "Лучшие X для дома, как выбрать X.", ["informational"]),
    ("home-problem-solving", "home", "Решение проблемы", "Как устранить X, что делать если X.", ["how_to", "informational"]),
    ("auto-howto-service", "auto", "Как сделать / обслужить", "Пошаговое обслуживание или ремонт.", ["how_to"]),
    ("auto-comparison", "auto", "Сравнение", "X vs Y.", ["informational"]),
    ("auto-top-choice", "auto", "Выбор / топ", "Как выбрать X, лучшие X.", ["informational"]),
    ("auto-problem-solving", "auto", "Решение проблемы", "Что делать если X.", ["how_to", "informational"]),
    ("auto-full-guide", "auto", "Полное руководство", "Всё про X в контексте эксплуатации.", ["informational"]),
    ("lifestyle-full-guide", "lifestyle", "Полное руководство", "Всё о X для здоровья и образа жизни.", ["informational"]),
    ("lifestyle-howto", "lifestyle", "How-To", "Как начать X, как делать X.", ["how_to"]),
    ("lifestyle-top-list", "lifestyle", "Топ / подборка", "Лучшие X.", ["informational"]),
    ("lifestyle-myths", "lifestyle", "Мифы и факты", "Правда о X, развенчание мифов.", ["informational"]),
    ("lifestyle-comparison", "lifestyle", "Сравнение подходов", "X vs Y, какой подход выбрать.", ["informational"]),
    ("pets-full-guide", "pets", "Полное руководство", "Всё об уходе за X.", ["informational"]),
    ("pets-howto", "pets", "How-To", "Как приучить / лечить / кормить.", ["how_to"]),
    ("pets-choice", "pets", "Выбор", "Как выбрать X, породы, корма.", ["informational"]),
    ("pets-problem-solving", "pets", "Решение проблемы", "Что делать если питомец X.", ["how_to", "informational"]),
    ("pets-comparison", "pets", "Сравнение", "X vs Y.", ["informational"]),
    ("garden-full-guide", "garden", "Полное руководство", "Всё о выращивании X.", ["informational"]),
    ("garden-howto", "garden", "Пошаговая инструкция", "Как посадить, ухаживать.", ["how_to"]),
    ("garden-seasonal", "garden", "Сезонный гайд", "Что делать в саду в X сезон.", ["informational", "how_to"]),
    ("garden-top-choice", "garden", "Выбор / топ", "Лучшие сорта, инструменты.", ["informational"]),
    ("garden-problem-solving", "garden", "Решение проблемы", "Болезни, вредители.", ["how_to", "informational"]),
    ("utility-service-guide", "utility", "Инструкция к сервису", "Как пользоваться X.", ["how_to"]),
    ("utility-howto", "utility", "How-To", "Как сделать X в сервисе или программе.", ["how_to"]),
    ("utility-comparison", "utility", "Сравнение сервисов", "X vs Y.", ["informational"]),
    ("utility-problem-solving", "utility", "Решение проблемы", "Как исправить ошибку X.", ["how_to"]),
    ("utility-full-guide", "utility", "Полное руководство", "Всё о X в контексте сервиса.", ["informational"]),
]

_niches_tbl = sa.table(
    "niches",
    sa.column("niche_id", sa.Text),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
)
_archetypes_tbl = sa.table(
    "archetypes",
    sa.column("archetype_id", sa.Text),
    sa.column("niche_id", sa.Text),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    sa.column("intent_triggers", postgresql.ARRAY(sa.Text)),
)


def upgrade() -> None:
    op.bulk_insert(
        _niches_tbl,
        [{"niche_id": n[0], "name": n[1], "description": n[2]} for n in NICHES],
    )
    op.bulk_insert(
        _archetypes_tbl,
        [
            {
                "archetype_id": a[0],
                "niche_id": a[1],
                "name": a[2],
                "description": a[3],
                "intent_triggers": a[4],
            }
            for a in ARCHETYPES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    arche_ids = tuple(a[0] for a in ARCHETYPES)
    niche_ids = tuple(n[0] for n in NICHES)
    bind.execute(
        sa.text("DELETE FROM archetypes WHERE archetype_id IN :ids").bindparams(
            sa.bindparam("ids", value=arche_ids, expanding=True)
        )
    )
    bind.execute(
        sa.text("DELETE FROM niches WHERE niche_id IN :ids").bindparams(
            sa.bindparam("ids", value=niche_ids, expanding=True)
        )
    )
