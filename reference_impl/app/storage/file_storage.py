"""
Файловое хранилище артефактов статьи.
Папка статьи: data/articles/{slug}_{article_id_short}/
"""
import logging
import re
from pathlib import Path
from app.config.settings import ARTICLES_DIR
from app.utils.file_utils import ensure_dir, write_json, write_text, read_json, read_text

logger = logging.getLogger(__name__)


def _transliterate(text: str) -> str:
    """Транслитерация русского текста в латиницу для имени папки."""
    table = {
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo",
        "ж":"zh","з":"z","и":"i","й":"j","к":"k","л":"l","м":"m",
        "н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
        "ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
        "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    }
    result = []
    for ch in text.lower():
        result.append(table.get(ch, ch))
    text = "".join(result)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    return text[:50]  # ограничиваем длину


def _make_folder_name(article_id: str, title: str = "") -> str:
    """Создаёт имя папки: slug_из_названия + короткий id."""
    short_id = article_id[:8]
    if title:
        slug = _transliterate(title)
        if slug:
            return f"{slug}_{short_id}"
    return article_id


def article_dir(article_id: str, title: str = "") -> Path:
    """Возвращает путь к папке статьи."""
    # Сначала ищем существующую папку по article_id
    for folder in ARTICLES_DIR.iterdir() if ARTICLES_DIR.exists() else []:
        if folder.is_dir() and article_id[:8] in folder.name:
            return folder
    # Создаём новую
    folder_name = _make_folder_name(article_id, title)
    return ARTICLES_DIR / folder_name


def create_article_folder(article_id: str, title: str = "") -> Path:
    path = article_dir(article_id, title)
    ensure_dir(path)
    ensure_dir(path / "sections")
    ensure_dir(path / "logs")
    ensure_dir(path / "prompts")
    return path


def save_artifact(article_id: str, filename: str, data: dict,
                  title: str = "") -> Path:
    path = article_dir(article_id, title) / filename
    write_json(path, data)
    return path


def save_markdown(article_id: str, content: str,
                  filename: str = "article.md", title: str = "") -> Path:
    path = article_dir(article_id, title) / filename
    write_text(path, content)
    logger.info(f"Статья сохранена: {path}")
    return path


def save_section_artifact(article_id: str, section_id: str,
                          stage: str, data: dict) -> Path:
    path = article_dir(article_id) / "sections" / f"{section_id}_{stage}.json"
    write_json(path, data)
    return path


def save_prompt(article_id: str, step_name: str,
                prompt: str, response: str) -> None:
    base = article_dir(article_id) / "prompts"
    write_text(base / f"{step_name}_prompt.txt", prompt)
    write_text(base / f"{step_name}_response.txt", response)


def load_artifact(article_id: str, filename: str) -> dict:
    path = article_dir(article_id) / filename
    return read_json(path)


def load_markdown(article_id: str, filename: str = "article.md") -> str:
    path = article_dir(article_id) / filename
    return read_text(path)
