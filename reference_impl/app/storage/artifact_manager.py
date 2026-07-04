"""
ArtifactManager — удобный фасад для сохранения всех артефактов статьи.
"""
import logging
from app.storage import file_storage as fs
from app.storage import repositories as repo

logger = logging.getLogger(__name__)

FILENAMES = {
    "article_input":              "article_input.json",
    "serp_bundle":                "serp_bundle.json",
    "competitor_analysis_report": "competitor_analysis_report.json",
    "brief":                      "brief.json",
    "outline":                    "outline.json",
    "full_draft":                 "full_draft.json",
    "qa_result":                  "qa_result.json",
    "final_package":              "final_package.json",
}


class ArtifactManager:
    def __init__(self, article_id: str, title: str = ""):
        self.article_id = article_id
        self.title      = title
        fs.create_article_folder(article_id, title)

    # ─── Сохранение ───────────────────────────────────────────────────────────

    def save(self, name: str, data: dict) -> None:
        filename = FILENAMES.get(name, f"{name}.json")
        fs.save_artifact(self.article_id, filename, data, self.title)

    def save_markdown(self, content: str) -> None:
        path = fs.save_markdown(self.article_id, content, title=self.title)
        logger.info(f"article.md → {path}")

    def save_section(self, section_id: str, stage: str, data: dict) -> None:
        fs.save_section_artifact(self.article_id, section_id, stage, data)

    def save_prompt(self, step_name: str, prompt: str, response: str) -> None:
        fs.save_prompt(self.article_id, step_name, prompt, response)

    # ─── Загрузка ─────────────────────────────────────────────────────────────

    def load(self, name: str) -> dict:
        filename = FILENAMES.get(name, f"{name}.json")
        return fs.load_artifact(self.article_id, filename)

    def load_markdown(self) -> str:
        return fs.load_markdown(self.article_id)

    # ─── БД ───────────────────────────────────────────────────────────────────

    def log_step_start(self, step_name: str) -> int:
        return repo.log_step_start(self.article_id, step_name)

    def log_step_finish(self, row_id: int, status: str = "done",
                        error: str = "") -> None:
        repo.log_step_finish(row_id, status, error)

    def update_status(self, status: str) -> None:
        repo.update_article_status(self.article_id, status)

    def update_qa(self, qa_status: str, qa_score: int) -> None:
        repo.update_article_qa(self.article_id, qa_status, qa_score)

    def upsert_section(self, section_id: str, status: str,
                       iterations: int, word_count: int) -> None:
        repo.upsert_section(self.article_id, section_id,
                            status, iterations, word_count)
