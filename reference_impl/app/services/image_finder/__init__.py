"""
Поиск картинок для статей. Слой провайдеров: Wikimedia → Unsplash → Pixabay.
Каждый провайдер возвращает {url, source_url, attribution} или None.
"""
from app.services.image_finder.base import ImageProvider, ImageResult
from app.services.image_finder.wikimedia import WikimediaProvider
from app.services.image_finder.unsplash import UnsplashProvider
from app.services.image_finder.pixabay import PixabayProvider


def get_providers() -> list[ImageProvider]:
    """
    Возвращает упорядоченный список провайдеров.
      Wikimedia — без ключа, точные фактические объекты (озёра, города, известные места).
      Pixabay   — большая база, понимает много языков (ru/de/it/fr...).
      Unsplash  — англоязычный, ставим последним; русские запросы выдают мусор.
    """
    return [
        PixabayProvider(),
        UnsplashProvider(),
        WikimediaProvider(),
    ]
