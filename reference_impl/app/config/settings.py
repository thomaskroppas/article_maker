"""
Общие настройки приложения.
Все пути, версии и глобальные параметры.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Корень проекта ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # /project_root

# ─── Пути к данным ────────────────────────────────────────────────────────────
DATA_DIR      = BASE_DIR / "data"
ARTICLES_DIR  = DATA_DIR / "articles"
LOGS_DIR      = BASE_DIR / "logs"
PROMPTS_DIR   = BASE_DIR / "prompts"

# Создать папки если не существуют
for _dir in [DATA_DIR, ARTICLES_DIR, LOGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ─── Версии ───────────────────────────────────────────────────────────────────
PIPELINE_VERSION    = "v1"
PROMPT_SET_VERSION  = "v1"
APP_VERSION         = "1.0.0"

# ─── SERP API ─────────────────────────────────────────────────────────────────
XMLSTOCK_API_URL = os.getenv(
    "XMLSTOCK_API_URL",
    "http://95.217.108.20:8085/api/v1/parsers/xmlstock/serp"
)

# ─── API ключи ────────────────────────────────────────────────────────────────
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY", "")
