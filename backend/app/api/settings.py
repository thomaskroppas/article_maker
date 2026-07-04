"""Settings API — ТЗ §10.10, §11.2.10."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..settings_service import SettingsService
from .deps import get_db, require_auth

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)])


@router.get("")
def get_settings_status(db: Session = Depends(get_db)) -> dict:
    return SettingsService(db).public_status()


@router.put("", status_code=204)
def update_settings(body: dict, db: Session = Depends(get_db)):
    SettingsService(db).update_many(body)
