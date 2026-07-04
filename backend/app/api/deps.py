"""Общие зависимости FastAPI: сессия БД и Basic Auth (ТЗ §11.1)."""

from __future__ import annotations

import secrets
from typing import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.session import SessionLocal

_security = HTTPBasic(auto_error=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    cfg = get_settings()
    user_ok = secrets.compare_digest(credentials.username, cfg.basic_auth_username)
    pass_ok = secrets.compare_digest(credentials.password, cfg.basic_auth_password or "")
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учётные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
