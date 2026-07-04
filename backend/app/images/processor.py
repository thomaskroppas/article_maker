"""Обработка картинки — ТЗ §6.11: resize 1920, crop 16:9, WebP q70."""

from __future__ import annotations

import io

_MAX_LONG_SIDE = 1920
_TARGET_RATIO = 16 / 9
_WEBP_QUALITY = 70


def process_image(raw: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(raw)).convert("RGB")

    # 1) resize до 1920 по длинной стороне (если больше)
    w, h = img.size
    longest = max(w, h)
    if longest > _MAX_LONG_SIDE:
        scale = _MAX_LONG_SIDE / longest
        img = img.resize((round(w * scale), round(h * scale)))
        w, h = img.size

    # 2) crop 16:9 из центра
    if w / h > _TARGET_RATIO:  # слишком широкое → режем по ширине
        new_w = round(h * _TARGET_RATIO)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:  # слишком высокое → режем по высоте
        new_h = round(w / _TARGET_RATIO)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    # 3) WebP quality 70
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=_WEBP_QUALITY)
    return out.getvalue()
