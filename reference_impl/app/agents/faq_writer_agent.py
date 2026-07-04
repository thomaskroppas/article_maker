"""
FAQ Writer агент. Пишет блок FAQ по вопросам из outline.faq_section.

Ответы оптимизированы под Google featured snippet: 40–60 слов,
прямой ответ в первом предложении, без вводных фраз.

Модель: Sonnet (та же что у Writer'а — важно чтобы стиль совпадал).
"""
import logging
import re
from typing import List, Optional

from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FAQWriterAgent(BaseAgent):
    agent_name = "faq_writer_agent"

    def run(self,
            article_input,
            brief,
            article_markdown: str,
            author: Optional[dict] = None) -> str:
        """
        article_input   — ArticleInput (для title, main_keyword).
        brief           — Brief (для lsi_keywords).
        article_markdown — уже собранная статья (для контекста и консистентности).
        author          — dict с полями автора (name/character/tone/age_image), опционально.

        Возвращает готовый markdown с блоком FAQ (## FAQ + вопросы/ответы),
        либо пустую строку если faq_section.enabled=False или вопросов нет.
        """
        questions = getattr(brief, 'faq_questions', None)  # заглушка на будущее
        # Реально вопросы приходят из outline; передаём отдельным аргументом
        # чтобы не тащить сюда весь outline.
        # См. вызов из pipeline_orchestrator.
        raise NotImplementedError(
            "Используй метод run_with_questions() — он принимает вопросы явно."
        )

    def run_with_questions(self,
                           article_input,
                           brief,
                           article_markdown: str,
                           questions: List[str],
                           author: Optional[dict] = None) -> str:
        """
        Основной метод. Возвращает markdown блока FAQ.
        Если что-то пошло не так — возвращает пустую строку (не роняем пайплайн).
        """
        if not questions:
            return ""

        # Готовим переменные для промпта
        author_block = self._format_author_block(author)
        article_summary = self._summarize_article(article_markdown, brief)
        questions_str = "\n".join(f"{i+1}. {q.strip()}" for i, q in enumerate(questions))

        variables = {
            "article_title":    article_input.article_title,
            "main_keyword":     article_input.main_keyword,
            "lsi_keywords":     ", ".join(brief.lsi_keywords) or "—",
            "author_block":     author_block,
            "questions":        questions_str,
            "article_summary":  article_summary,
        }

        try:
            resp = self._call(variables)
        except Exception as e:
            logger.warning(f"[faq_writer] LLM-вызов упал: {e}")
            return ""

        text = (resp.text or "").strip()
        if not text:
            return ""

        # Снимаем ``` обёртки если LLM решил их добавить
        text = re.sub(r"^```(?:markdown)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
        text = text.strip()

        # Валидация: должен быть заголовок FAQ
        if "faq" not in text.lower()[:200]:
            # LLM забыл добавить ## FAQ — добавим
            text = "## FAQ\n\n" + text

        logger.info(f"[faq_writer] сгенерирован FAQ ({len(questions)} вопросов)")
        return text

    def _format_author_block(self, author: Optional[dict]) -> str:
        if not author:
            return "Автор не задан — пиши нейтральным редакторским голосом."
        parts = []
        name = author.get("name")
        if name:
            parts.append(f"Тебя зовут {name}.")
        tone = author.get("tone")
        if tone:
            parts.append(f"Твой тон: {tone}.")
        character = author.get("character")
        if character:
            parts.append(f"Твой характер: {character}")
        return "\n".join(parts) or "—"

    def _summarize_article(self, markdown: str, brief=None) -> str:
        """
        Собираем компактный контекст для FAQ-агента, чтобы он не противоречил
        уже написанной статье. Включаем:
        1. Первый абзац (для стиля и общего smыcла).
        2. H2-заголовки (карта статьи).
        3. must_cover из брифа — точные формулировки ключевых фактов.
        4. Все предложения статьи с цифрами (км, м, %, годы) — реальные факты
           как они прозвучали в тексте.
        """
        lines = markdown.split("\n")

        # 1. Первый содержательный абзац (после H1)
        first_para = ""
        for line in lines:
            if line.startswith("#"):
                continue
            if line.strip() and not line.startswith("!") and not line.startswith("["):
                first_para = line.strip()
                break

        # 2. H2-заголовки — карта статьи
        h2_titles = [
            line[3:].strip()
            for line in lines
            if line.startswith("## ") and not line.startswith("## FAQ")
        ]
        headings = "\n".join(f"- {t}" for t in h2_titles[:15]) or "—"

        # 3. must_cover из брифа — эталонные формулировки фактов
        must_cover_str = "—"
        if brief and getattr(brief, "must_cover", None):
            must_cover_str = "\n".join(
                f"- {item}" for item in brief.must_cover[:20]
            )

        # 4. Все строки с цифрами из статьи (реальные факты как в тексте)
        # Разбиваем на предложения и фильтруем — оставляем те где есть
        # число + единица измерения / год / процент.
        text_only = "\n".join(
            l for l in lines
            if not l.startswith("#") and not l.startswith("!")
            and not l.startswith("[") and not l.startswith("|")
        )
        # Простой sentence split по .!? с учётом кириллицы
        sentences = re.split(r"(?<=[.!?])\s+", text_only)
        fact_regex = re.compile(
            r"\d+[\s\u00a0]*(?:м|км|км²|км³|м³|%|тыс|млн|млрд|лет|года?|век|"
            r"мировых|метр|километр|процент|градус|°|С)",
            re.IGNORECASE | re.UNICODE
        )
        facts = []
        for s in sentences:
            s = s.strip()
            if 20 < len(s) < 300 and fact_regex.search(s):
                facts.append(s)
        facts_str = "\n".join(f"- {f}" for f in facts[:15]) or "—"

        return (
            f"Первый абзац статьи:\n{first_para[:400]}\n\n"
            f"Секции статьи:\n{headings}\n\n"
            f"Ключевые факты из ТЗ (точные формулировки):\n{must_cover_str}\n\n"
            f"Реальные факты из текста статьи (как написано):\n{facts_str}"
        )
