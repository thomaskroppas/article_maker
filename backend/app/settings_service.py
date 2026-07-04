"""Настройки приложения — ТЗ §10.10.

Значения хранятся в app_settings зашифрованными Fernet (ключ SETTINGS_ENCRYPTION_KEY).
Приоритет чтения: БД → .env. Worker/backend читают актуальные значения при каждом
обращении (смена ключа применяется без рестарта). GET-статус ключей не раскрывает.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .config import get_settings
from .db.models import AppSetting

# Ключи-настройки и их соответствие env-переменным (fallback).
_ENV_FALLBACK = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "serper_api_key": "SERPER_API_KEY",
    "serp_provider": "SERP_PROVIDER",
    "xmlstock_api_url": "XMLSTOCK_API_URL",
    "pixabay_api_keys": "PIXABAY_API_KEYS",
    "unsplash_api_keys": "UNSPLASH_API_KEYS",
}

# Секретные ключи — в GET /settings возвращается только «задан/не задан».
_SECRET_KEYS = {
    "anthropic_api_key",
    "serper_api_key",
    "pixabay_api_keys",
    "unsplash_api_keys",
}


def _fernet():
    from cryptography.fernet import Fernet

    key = get_settings().settings_encryption_key
    if not key:
        raise RuntimeError("SETTINGS_ENCRYPTION_KEY не задан — шифрование настроек невозможно")
    return Fernet(key.encode() if isinstance(key, str) else key)


class SettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str) -> Optional[str]:
        """Значение настройки: БД (расшифровка) → .env fallback."""
        row = self.db.get(AppSetting, key)
        if row is not None:
            try:
                return _fernet().decrypt(row.value.encode()).decode()
            except Exception:  # noqa: BLE001 — повреждённое/не то значение → fallback
                pass
        env_name = _ENV_FALLBACK.get(key)
        if env_name:
            return os.environ.get(env_name) or None
        return None

    def set(self, key: str, value: str) -> None:
        token = _fernet().encrypt(value.encode()).decode()
        row = self.db.get(AppSetting, key)
        if row is None:
            self.db.add(AppSetting(key=key, value=token))
        else:
            row.value = token
            row.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    def _count(self, key: str) -> int:
        val = self.get(key)
        return len([x for x in val.split(",") if x.strip()]) if val else 0

    def public_status(self) -> dict:
        """GET /api/settings — без раскрытия секретов (§10.10)."""
        return {
            "anthropic_key_set": bool(self.get("anthropic_api_key")),
            "serper_key_set": bool(self.get("serper_api_key")),
            "pixabay_keys_count": self._count("pixabay_api_keys"),
            "unsplash_keys_count": self._count("unsplash_api_keys"),
            "serp_provider": self.get("serp_provider") or "serper",
            "xmlstock_url": self.get("xmlstock_api_url") or "",
        }

    def update_many(self, values: dict) -> None:
        for key, value in values.items():
            if value is None or value == "":
                continue
            self.set(key, str(value))
