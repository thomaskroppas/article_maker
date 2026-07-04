"""Подключение к БД: engine + фабрика сессий."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


def _make_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session() -> Session:
    return SessionLocal()
