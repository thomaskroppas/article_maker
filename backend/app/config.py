"""Конфигурация приложения.

Инфраструктурные значения читаются из окружения (.env / docker-compose).
API-ключи внешних сервисов в первом релизе хранятся в БД (`app_settings`,
приоритет БД → .env) — это будет реализовано в T-11; здесь задаются только
значения-по-умолчанию из окружения для первого старта.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Инфраструктура ---
    database_url: str = "postgresql://seo:seo@postgres:5432/seo_pipeline"
    redis_url: str = "redis://redis:6379/0"

    # --- Basic auth ---
    basic_auth_username: str = "admin"
    basic_auth_password: str = ""

    # --- Шифрование настроек (T-11) ---
    settings_encryption_key: str = ""
    wp_encryption_key: str = ""

    # --- Внешние сервисы (fallback из окружения; приоритет у БД, см. T-11) ---
    anthropic_api_key: str = ""
    serp_provider: str = "serper"          # serper | xmlstock
    serper_api_key: str = ""
    xmlstock_api_url: str = ""
    pixabay_api_keys: str = ""
    unsplash_api_keys: str = ""

    # --- CORS (dev): фронт на :3000 обращается к API на :8000 напрямую ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
