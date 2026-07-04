"""ArticleInput — ТЗ 13.1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from .base import SchemaBase
from .legacy_compat import (
    ALLOWED_REQUIRED_ELEMENTS,
    normalize_required_elements,
    normalize_string_list,
)


class ArticleInput(SchemaBase):
    # системные
    article_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pipeline_version: str = "v1"
    prompt_set_version: str = "v1"

    # основные
    site_domain: str = Field(default="example.net", min_length=3, max_length=253)
    author_id: Optional[str] = None
    article_title: str = Field(..., min_length=5, max_length=300)
    main_keyword: str = Field(..., min_length=2, max_length=300)
    secondary_keywords: List[str] = Field(..., min_length=1)

    # длина
    length_strategy: str = Field(
        default="match_top",
        pattern=r"^(shorter_top|match_top|longer_top|custom)$",
    )
    target_word_count: Optional[int] = Field(default=None, ge=300, le=10000)

    # язык
    language: str = Field(..., pattern=r"^(ru|en|de|it|es|fr)$")
    geo: str = Field(..., min_length=2, max_length=150)

    # тип статьи
    intent: str = Field(..., pattern=r"^(informational|how_to)$")
    article_type: str = Field(..., pattern=r"^(informational|how_to)$")
    difficulty: str = Field(..., pattern=r"^(easy|medium|hard)$")
    style_archetype: str = Field(
        ...,
        pattern=r"^(expert_clear|friendly_practical|calm_analytical|editorial_neutral)$",
    )

    # ограничения
    forbidden_words: List[str] = Field(default_factory=list)
    required_elements: List[str] = Field(...)
    optional_notes: Optional[str] = Field(default=None, max_length=5000)

    # настройки пайплайна
    review_outline: bool = True
    enable_section_critic: bool = True
    force_refresh_serp: bool = False

    # SERP
    serp_json_path: Optional[str] = None
    manual_sources: Optional[List[str]] = None

    @model_validator(mode="before")
    @classmethod
    def _legacy_and_lists(cls, data):
        # legacy desktop-format compatibility + дедупликация списков (ТЗ 13.1)
        if isinstance(data, dict):
            data = dict(data)
            if "required_elements" in data:
                data["required_elements"] = normalize_required_elements(
                    data["required_elements"]
                )
            if "secondary_keywords" in data:
                data["secondary_keywords"] = normalize_string_list(
                    data["secondary_keywords"]
                )
            if data.get("forbidden_words") is not None:
                data["forbidden_words"] = normalize_string_list(data["forbidden_words"])
            if data.get("manual_sources") is not None:
                data["manual_sources"] = normalize_string_list(data["manual_sources"])
        return data

    @field_validator("required_elements")
    @classmethod
    def _required_subset(cls, v: List[str]) -> List[str]:
        bad = [x for x in v if x not in ALLOWED_REQUIRED_ELEMENTS]
        if bad:
            raise ValueError(
                f"required_elements содержит недопустимые элементы: {bad}; "
                f"допустимы {sorted(ALLOWED_REQUIRED_ELEMENTS)}"
            )
        return v

    @model_validator(mode="after")
    def _custom_needs_word_count(self):
        if self.length_strategy == "custom" and self.target_word_count is None:
            raise ValueError(
                "target_word_count обязателен при length_strategy='custom'"
            )
        return self
