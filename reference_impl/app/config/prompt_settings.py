"""
Реестр промптов: агент → версия → путь к файлу.
"""
from app.config.settings import PROMPTS_DIR

PROMPT_VERSION = "v1"

PROMPT_REGISTRY = {
    "competitor_analysis_agent": PROMPTS_DIR / "competitor_analysis_agent" / f"{PROMPT_VERSION}.txt",
    "brief_agent":               PROMPTS_DIR / "brief_agent"               / f"{PROMPT_VERSION}.txt",
    "outline_agent":             PROMPTS_DIR / "outline_agent"             / f"{PROMPT_VERSION}.txt",
    "writer_agent":              PROMPTS_DIR / "writer_agent"              / f"{PROMPT_VERSION}.txt",
    "critic_agent":              PROMPTS_DIR / "critic_agent"              / f"{PROMPT_VERSION}.txt",
    "editor_agent":              PROMPTS_DIR / "editor_agent"              / f"{PROMPT_VERSION}.txt",
    "final_qa_agent":            PROMPTS_DIR / "final_qa_agent"            / f"{PROMPT_VERSION}.txt",
    "metadata_agent":            PROMPTS_DIR / "metadata_agent"            / f"{PROMPT_VERSION}.txt",
    "archetype_picker_agent":    PROMPTS_DIR / "archetype_picker_agent"    / f"{PROMPT_VERSION}.txt",
    "style_extractor_agent":     PROMPTS_DIR / "style_extractor_agent"     / f"{PROMPT_VERSION}.txt",
    "faq_writer_agent":          PROMPTS_DIR / "faq_writer_agent"          / f"{PROMPT_VERSION}.txt",
    "lsi_agent":                 PROMPTS_DIR / "lsi_agent"                 / f"{PROMPT_VERSION}.txt",
}
