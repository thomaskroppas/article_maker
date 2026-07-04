"""initial schema + pgvector extension + analytics MV

Revision ID: 0001
Revises:
Create Date: 2026-07-04

ТЗ раздел 12 (таблицы, индексы, материализованный view) + 10.10 (app_settings).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = postgresql.TIMESTAMP(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    # pgvector — нужен для каталога Стратегии C (T-18); расширение включаем сразу.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "niches",
        sa.Column("niche_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
    )

    op.create_table(
        "archetypes",
        sa.Column("archetype_id", sa.Text(), primary_key=True),
        sa.Column("niche_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("intent_triggers", postgresql.ARRAY(sa.Text())),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.niche_id"]),
    )

    op.create_table(
        "sites",
        sa.Column("domain", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("niche_id", sa.Text()),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("wordpress_url", sa.Text()),
        sa.Column("wordpress_user", sa.Text()),
        sa.Column("wordpress_password", sa.Text()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.niche_id"]),
    )

    op.create_table(
        "style_references",
        sa.Column("reference_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("geo", sa.Text(), nullable=False),
        sa.Column("niche_tags", postgresql.ARRAY(sa.Text())),
        sa.Column("notes", sa.Text()),
        sa.Column("reference_text", sa.Text()),
        sa.Column("extracted_style", sa.Text()),
        sa.Column("extracted_tone", sa.Text()),
        sa.Column("extracted_age_image", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
    )
    op.create_index("idx_style_references_language", "style_references", ["language"])
    op.create_index(
        "idx_style_references_niche_tags",
        "style_references",
        ["niche_tags"],
        postgresql_using="gin",
    )

    op.create_table(
        "authors",
        sa.Column("author_id", sa.Text(), primary_key=True),
        sa.Column("site_domain", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("character", sa.Text()),
        sa.Column("tone", sa.Text()),
        sa.Column("age_image", sa.Text()),
        sa.Column("niche_id", sa.Text()),
        sa.Column("reference_id", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(["site_domain"], ["sites.domain"]),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.niche_id"]),
        sa.ForeignKeyConstraint(["reference_id"], ["style_references.reference_id"]),
    )
    op.create_index("idx_authors_site_domain", "authors", ["site_domain"])

    op.create_table(
        "articles",
        sa.Column("article_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("site_domain", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Text()),
        sa.Column("archetype_id", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("main_keyword", sa.Text()),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("qa_status", sa.Text()),
        sa.Column("qa_score", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default=sa.text("0")),
        sa.Column("generation_time_seconds", sa.Integer()),
        sa.Column("input_data", postgresql.JSONB()),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(["site_domain"], ["sites.domain"]),
        sa.ForeignKeyConstraint(["author_id"], ["authors.author_id"]),
        sa.ForeignKeyConstraint(["archetype_id"], ["archetypes.archetype_id"]),
    )
    op.create_index("idx_articles_site_domain", "articles", ["site_domain"])
    op.create_index("idx_articles_created_at", "articles", [sa.text("created_at DESC")])
    op.create_index("idx_articles_status", "articles", ["status"])

    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True)),
        sa.Column("step_name", sa.Text(), nullable=False),
        sa.Column("step_number", sa.Integer()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("tokens_in", sa.Integer()),
        sa.Column("tokens_out", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.article_id"], ondelete="CASCADE"
        ),
    )
    op.create_index("idx_pipeline_steps_article_id", "pipeline_steps", ["article_id"])

    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True)),
        sa.Column("section_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("iterations", sa.Integer(), server_default=sa.text("0")),
        sa.Column("word_count", sa.Integer(), server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.article_id"], ondelete="CASCADE"
        ),
    )
    op.create_index("idx_sections_article_id", "sections", ["article_id"])

    op.create_table(
        "archetype_picks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True)),
        sa.Column("suggested_archetype_id", sa.Text()),
        sa.Column("chosen_archetype_id", sa.Text()),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("niche_id", sa.Text()),
        sa.Column("intent", sa.Text()),
        sa.Column("created_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.article_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["suggested_archetype_id"], ["archetypes.archetype_id"]
        ),
        sa.ForeignKeyConstraint(["chosen_archetype_id"], ["archetypes.archetype_id"]),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.niche_id"]),
    )

    op.create_table(
        "fact_check_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True)),
        sa.Column("total_statements", sa.Integer()),
        sa.Column("verified", sa.Integer()),
        sa.Column("mismatches", sa.Integer()),
        sa.Column("uncertain", sa.Integer()),
        sa.Column("results_json", postgresql.JSONB()),
        sa.Column("checked_at", TS, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["article_id"], ["articles.article_id"], ondelete="CASCADE"
        ),
    )
    op.create_index("idx_fact_check_article_id", "fact_check_results", ["article_id"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", TS, nullable=False, server_default=NOW),
    )

    # Аналитический материализованный view (ТЗ 12.2)
    op.execute(
        """
        CREATE MATERIALIZED VIEW mv_articles_by_site_month AS
        SELECT
            site_domain,
            DATE_TRUNC('month', created_at) AS month,
            COUNT(*) AS total,
            AVG(qa_score) AS avg_qa,
            SUM(cost_usd) AS total_cost
        FROM articles
        WHERE status = 'completed'
        GROUP BY site_domain, DATE_TRUNC('month', created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_articles_by_site_month")
    op.drop_table("app_settings")
    op.drop_index("idx_fact_check_article_id", table_name="fact_check_results")
    op.drop_table("fact_check_results")
    op.drop_table("archetype_picks")
    op.drop_index("idx_sections_article_id", table_name="sections")
    op.drop_table("sections")
    op.drop_index("idx_pipeline_steps_article_id", table_name="pipeline_steps")
    op.drop_table("pipeline_steps")
    op.drop_index("idx_articles_status", table_name="articles")
    op.drop_index("idx_articles_created_at", table_name="articles")
    op.drop_index("idx_articles_site_domain", table_name="articles")
    op.drop_table("articles")
    op.drop_index("idx_authors_site_domain", table_name="authors")
    op.drop_table("authors")
    op.drop_index("idx_style_references_niche_tags", table_name="style_references")
    op.drop_index("idx_style_references_language", table_name="style_references")
    op.drop_table("style_references")
    op.drop_table("sites")
    op.drop_table("archetypes")
    op.drop_table("niches")
    op.execute("DROP EXTENSION IF EXISTS vector")
