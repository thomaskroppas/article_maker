"""FinalPackage и вложенные схемы — ТЗ 13.9."""

from __future__ import annotations

from typing import List

from .base import SchemaBase


class FaqItem(SchemaBase):
    question: str
    answer: str


class SchemaBlock(SchemaBase):
    type: str = "FAQPage"
    data: dict


class FinalPackage(SchemaBase):
    article_id: str
    slug: str
    meta_title: str
    meta_description: str
    article_markdown: str
    faq: List[FaqItem]
    schema_data: SchemaBlock
    category: str
    tags: List[str]
    internal_links_suggestions: List[str]
