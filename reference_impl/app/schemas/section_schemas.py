from __future__ import annotations
from typing import List
from pydantic import BaseModel


class SectionDraft(BaseModel):
    section_id: str
    title:      str = ""
    content:    str = ""
    word_count: int = 0
    iteration:  int = 1

    def to_dict(self) -> dict:
        return self.model_dump()


class ReviewReport(BaseModel):
    section_id:       str
    status:           str = "ok"          # ok | needs_revision
    issues:           List[str] = []
    fix_instructions: List[str] = []
    iteration:        int = 1

    @property
    def needs_revision(self) -> bool:
        return self.status == "needs_revision"

    def to_dict(self) -> dict:
        return self.model_dump()


class PatchedSection(BaseModel):
    section_id: str
    title:      str = ""
    content:    str = ""
    word_count: int = 0
    iteration:  int = 1

    def to_dict(self) -> dict:
        return self.model_dump()
