"""Общая база схем.

extra="ignore" — Pydantic-дефолт; фиксируем явно: реальные файлы содержат
legacy-поля сверх §13, которые молча отбрасываются на входе (и потому не
попадают в выходной контракт §13).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
