"""
Схема article_input — основной входной объект пайплайна.
SERP-данные загружаются из JSON файла краулера, не вводятся вручную.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid


class ArticleInput(BaseModel):
    # ─── Системные поля ───────────────────────────────────────────────────────
    article_id:         str      = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at:         datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:         datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status:             str      = "created"
    pipeline_version:   str      = "v1"
    prompt_set_version: str      = "v1"

    # ─── Основные поля ────────────────────────────────────────────────────────
    site_domain:        str = Field(default="example.net", min_length=3, max_length=253)
    author_id:          Optional[str] = Field(default=None)
    article_title:      str = Field(..., min_length=5, max_length=300)
    main_keyword:       str = Field(..., min_length=2, max_length=300)
    secondary_keywords: List[str] = Field(..., min_length=1)
    length_strategy:    str = Field(
        default="match_top",
        pattern=r"^(shorter_top|match_top|longer_top|custom)$"
    )
    target_word_count:  Optional[int] = Field(default=None, ge=300, le=10000)
    language:           str = Field(..., pattern=r"^[a-z]{2}$")
    geo:                str = Field(..., min_length=2, max_length=150)
    intent:             str = Field(..., pattern=r"^(informational|how_to)$")
    article_type:       str = Field(..., pattern=r"^(informational|how_to)$")
    difficulty:         str = Field(..., pattern=r"^(easy|medium|hard)$")
    style_archetype:    str = Field(
        ...,
        pattern=r"^(expert_clear|friendly_practical|calm_analytical|editorial_neutral)$"
    )

    # ─── Ограничения ──────────────────────────────────────────────────────────
    forbidden_words:   List[str] = Field(default_factory=list)
    required_elements: List[str] = Field(...)
    optional_notes:    Optional[str] = Field(default=None, max_length=5000)

    # ─── Настройки пайплайна ──────────────────────────────────────────────────
    always_review_sections: bool = True
    force_refresh_serp:     bool = False

    # ─── SERP и источники ────────────────────────────────────────────────────
    serp_json_path:  Optional[str]       = None
    manual_sources:  Optional[List[str]] = None

    # ─── Валидаторы ───────────────────────────────────────────────────────────
    @field_validator("secondary_keywords", "forbidden_words", "required_elements",
                     mode="before")
    @classmethod
    def clean_list(cls, v):
        if isinstance(v, str):
            v = [line.strip() for line in v.splitlines()]
        if isinstance(v, list):
            seen = set()
            result = []
            for item in v:
                item = str(item).strip()
                if item and item not in seen:
                    seen.add(item)
                    result.append(item)
            return result
        return v

    @field_validator("article_title", "main_keyword", "geo", mode="before")
    @classmethod
    def strip_string(cls, v):
        return str(v).strip() if v else v

    @field_validator("target_word_count", mode="before")
    @classmethod
    def to_int(cls, v):
        if v is None or v == "" or v == "null":
            return None
        return int(v)

    @field_validator("target_word_count", mode="after")
    @classmethod
    def custom_needs_count(cls, v, info):
        # Если стратегия custom — target_word_count обязателен
        strategy = info.data.get("length_strategy")
        if strategy == "custom" and v is None:
            raise ValueError(
                "target_word_count обязателен при length_strategy='custom'"
            )
        return v

    @field_validator("required_elements", mode="after")
    @classmethod
    def validate_required_elements(cls, v):
        allowed = {"faq", "quick_answer", "table", "list", "conclusion", "sources_block"}
        for el in v:
            if el not in allowed:
                raise ValueError(f"Недопустимый элемент: {el}. Допустимые: {allowed}")
        return v

    def to_dict(self) -> dict:
        data = self.model_dump()
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data
