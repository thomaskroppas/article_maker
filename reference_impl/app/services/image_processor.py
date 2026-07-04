"""
Загрузка картинок по URL, обрезка под 16:9 из центра, сжатие в WebP.
Сохраняем в data/articles/<slug>_<id>/images/N.webp.
В markdown ссылка относительная: images/N.webp.

Параметры — из webp_converter (quality=70, method=6).
Добавили resize до 1920px по длинной стороне перед обрезкой,
чтобы избежать чрезмерно тяжёлых файлов с Wikimedia (4000px+).
"""
import io
import logging
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


# Пресет качества WebP, как в инструменте webp_converter (SEO-режим)
WEBP_QUALITY = 70
# Метод компрессии: 6 даёт лучший размер при медленной обработке
WEBP_METHOD = 6
# Максимальный размер по длинной стороне перед обрезкой
MAX_DIMENSION = 1920
# Целевое соотношение сторон (ширина : высота)
TARGET_RATIO = (16, 9)

_DOWNLOAD_HEADERS = {
    "User-Agent": "SEO-Pipeline/1.0 (https://github.com/thomaskroppas/ai_articles_pipeline)"
}


def _download(url: str, timeout: int = 15) -> Optional[bytes]:
    """Скачивает картинку по URL. None при ошибке."""
    try:
        r = requests.get(url, headers=_DOWNLOAD_HEADERS, timeout=timeout, stream=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.warning(f"[image_proc] не удалось скачать {url[:80]}...: {e}")
        return None


def _load_image(data: bytes) -> Optional[Image.Image]:
    """Декодирует байты в Image (RGB). None при ошибке."""
    try:
        img = Image.open(io.BytesIO(data))
        # Конвертация прозрачных в RGB на белом фоне (Wikimedia часто PNG)
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            return bg
        if img.mode != "RGB":
            return img.convert("RGB")
        return img
    except Exception as e:
        logger.warning(f"[image_proc] не удалось декодировать картинку: {e}")
        return None


def _resize_if_huge(img: Image.Image, max_side: int = MAX_DIMENSION) -> Image.Image:
    """Уменьшает картинку до max_side по длинной стороне (пропорции сохраняются)."""
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img
    scale = max_side / longest
    new_w, new_h = int(w * scale), int(h * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _center_crop_16_9(img: Image.Image) -> Image.Image:
    """
    Обрезает картинку под 16:9 из центра.
    Берём максимальный прямоугольник 16:9, помещающийся в исходник.
    """
    rw, rh = TARGET_RATIO
    w, h = img.size
    src_ratio = w / h
    tgt_ratio = rw / rh

    if src_ratio > tgt_ratio:
        # Шире чем 16:9 → режем по бокам
        new_w = int(h * tgt_ratio)
        x = (w - new_w) // 2
        return img.crop((x, 0, x + new_w, h))
    else:
        # Уже чем 16:9 → режем сверху/снизу
        new_h = int(w / tgt_ratio)
        y = (h - new_h) // 2
        return img.crop((0, y, w, y + new_h))


def _save_webp(img: Image.Image, out_path: Path) -> int:
    """Сохраняет в WebP, возвращает размер файла в байтах."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    return out_path.stat().st_size


def fetch_and_compress(url: str, out_path: Path) -> Optional[Path]:
    """
    Скачивает картинку по URL, обрезает 16:9 из центра, жмёт в WebP.
    Возвращает Path сохранённого файла или None при ошибке.
    """
    raw = _download(url)
    if raw is None:
        return None
    img = _load_image(raw)
    if img is None:
        return None
    try:
        img = _resize_if_huge(img)
        img = _center_crop_16_9(img)
        size = _save_webp(img, out_path)
        logger.info(f"[image_proc] {out_path.name}: {size // 1024} KB ({img.size[0]}x{img.size[1]})")
        return out_path
    except Exception as e:
        logger.warning(f"[image_proc] обработка упала: {e}")
        return None
