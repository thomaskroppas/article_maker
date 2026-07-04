"""
Базовый интерфейс провайдера картинок.
Конкретные провайдеры (Wikimedia, Unsplash, Pixabay) наследуются от ImageProvider.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageResult:
    url:         str   # прямая ссылка на картинку (для <img src>)
    source_url:  str   # страница-источник (для подписи «Источник»)
    attribution: str   # имя автора/проекта (например "Wikimedia Commons" или "John Smith on Unsplash")


class ImageProvider:
    """
    Базовый интерфейс. Наследники должны реализовать search().
    is_available() — провайдер готов работать (например, есть ключ).
    """

    name: str = "base"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, language: str = "ru") -> Optional[ImageResult]:
        """
        Возвращает первый подходящий результат поиска или None.
        language — двухбуквенный код языка запроса.
        Реализация через search_many — берём первый из списка.
        """
        results = self.search_many(query, language=language, limit=1)
        return results[0] if results else None

    def search_many(self, query: str, language: str = "ru",
                    limit: int = 5) -> list["ImageResult"]:
        """Возвращает несколько результатов — для дедупликации между точками."""
        raise NotImplementedError
