"""
PipelineOrchestrator — мозг системы.
Управляет всем жизненным циклом статьи от input до final_package.
"""
import logging
import threading
from typing import Callable, Optional

from app.config.pipeline_settings import (
    STATUS_INPUT_VALIDATED, STATUS_SERP_DONE, STATUS_COMPETITOR_DONE,
    STATUS_BRIEF_DONE, STATUS_OUTLINE_DONE, STATUS_SECTIONS_PROGRESS,
    STATUS_DRAFT_READY, STATUS_QA_DONE, STATUS_COMPLETED,
    STATUS_FAILED, STATUS_STOPPED,
    FINAL_STATUS_READY, FINAL_STATUS_READY_WARN, FINAL_STATUS_FAILED,
    QA_SCORE_PASS, QA_SCORE_WARN,
)
from app.llm.llm_client import LLMClient
from app.agents import (
    CompetitorAnalysisAgent, BriefAgent, OutlineAgent,
    WriterAgent, CriticAgent, EditorAgent,
    FinalQAAgent, MetadataAgent,
)
from app.orchestrator.section_pipeline import run_section
from app.orchestrator.status_manager import StatusManager
from app.services.serp_loader import load_from_file, load_from_cache
from app.services.markdown_builder import assemble_draft
from app.services import agent_cache
from app.schemas.competitor_analysis_report import CompetitorAnalysisReport
from app.schemas.brief import Brief
from app.schemas.outline import Outline
from app.storage.artifact_manager import ArtifactManager
from app.storage.repositories import upsert_article, get_authors_for_site
from app.schemas.article_input import ArticleInput
import random
logger = logging.getLogger(__name__)


class PipelineResult:
    def __init__(self, status: str, article_id: str,
                 final_status: str = "", qa_score: int = 0,
                 error: str = ""):
        self.status       = status        # "success" | "failed" | "stopped"
        self.article_id   = article_id
        self.final_status = final_status
        self.qa_score     = qa_score
        self.error        = error


class PipelineOrchestrator:
    def __init__(self,
                 on_status:       Optional[Callable[[str, str], None]] = None,
                 on_log:          Optional[Callable[[str], None]] = None,
                 on_prompt:       Optional[Callable[[str, str, str], None]] = None,
                 on_review_ready: Optional[Callable[[dict], None]] = None):
        """
        on_status(step_name, status) — обновление статусов для GUI
        on_log(message)             — строка лога для GUI
        on_prompt(step, prompt, response) — prompt/response для GUI
        on_review_ready(data)       — пауза для ревью outline пользователем
        """
        self._on_status       = on_status
        self._on_log          = on_log
        self._on_prompt       = on_prompt
        self._on_review_ready = on_review_ready
        self._stop_flag       = threading.Event()
        self._pause_event     = threading.Event()
        self._pause_event.set()          # изначально не на паузе
        self._reviewed_outline: Optional[dict] = None  # данные от GUI после ревью

        self.llm = LLMClient()

        # Агенты
        from app.agents.lsi_agent import LSIAgent
        self.competitor_agent = CompetitorAnalysisAgent(self.llm)
        self.lsi_agent        = LSIAgent(self.llm)
        self.brief_agent      = BriefAgent(self.llm)
        self.outline_agent    = OutlineAgent(self.llm)
        self.writer_agent     = WriterAgent(self.llm)
        self.critic_agent     = CriticAgent(self.llm)
        self.editor_agent     = EditorAgent(self.llm)
        self.qa_agent         = FinalQAAgent(self.llm)
        self.metadata_agent   = MetadataAgent(self.llm)

        # Пробрасываем stop_flag во все агенты для прерывания retry
        for agent in [self.competitor_agent, self.lsi_agent, self.brief_agent,
                      self.outline_agent, self.writer_agent,
                      self.critic_agent, self.editor_agent,
                      self.qa_agent, self.metadata_agent]:
            agent.set_stop_flag(self._stopped)

    # ─── Управление ───────────────────────────────────────────────────────────

    def stop(self):
        """Вызывается из GUI при нажатии кнопки Stop."""
        self._stop_flag.set()
        self._pause_event.set()   # разблокируем ожидание чтобы поток завершился

    def resume_with_outline(self, outline_data: dict):
        """Вызывается из GUI после того как пользователь подтвердил/изменил outline."""
        self._reviewed_outline = outline_data
        self._pause_event.set()  # снимаем паузу

    def _get_archetype_alternatives(self, niche_id):
        """
        Возвращает список архетипов ниши для dropdown в UI-блоке выбора.
        Если ниша не задана — пустой список.
        """
        if not niche_id:
            return []
        try:
            from app.storage.repositories import get_archetypes_for_niche
            archetypes = get_archetypes_for_niche(niche_id)
            return [
                {"archetype_id": a["archetype_id"],
                 "name_ru": a["name_ru"],
                 "description": a.get("description")}
                for a in archetypes
            ]
        except Exception as e:
            logger.warning(f"Не удалось получить альтернативы архетипа: {e}")
            return []

    def _stopped(self) -> bool:
        return self._stop_flag.is_set()

    def _log(self, msg: str):
        logger.info(msg)
        if self._on_log:
            self._on_log(msg)

    def _save_prompt(self, step: str, agent):
        if self._on_prompt:
            self._on_prompt(step, agent.last_prompt, agent.last_response)

    # ─── Главный метод ────────────────────────────────────────────────────────

    def run_pipeline(self, article_input: ArticleInput) -> PipelineResult:
        self._stop_flag.clear()
        aid = article_input.article_id

        # Сбрасываем счётчик статьи и привязываем его к новому article_id —
        # cost_tracker.add() будет писать накопленный расход в БД (поле cost_usd).
        from app.services.cost_tracker import cost_tracker
        cost_tracker.reset_article(aid)

        # Выбор автора из пула сайта.
        # Если автор уже задан в ArticleInput (ручной выбор) — оставляем его.
        # Иначе берём случайного активного автора сайта.
        # Если у сайта нет ни одного активного автора — это ошибка конфигурации:
        # генерация без автора недопустима, так как теряется смысл сущности.
        if not article_input.author_id:
            pool = get_authors_for_site(article_input.site_domain, only_active=True)
            if not pool:
                raise ValueError(
                    f"У сайта '{article_input.site_domain}' нет активных авторов. "
                    f"Создайте хотя бы одного автора для сайта перед генерацией."
                )
            chosen = random.choice(pool)
            article_input.author_id = chosen["author_id"]
            logger.info(
                f"Автор для статьи: {chosen['name']} ({chosen['author_id']})"
            )

        # Регистрируем статью в БД
        upsert_article(
            aid,
            article_input.site_domain,
            article_input.author_id,
            article_input.article_title,
            article_input.main_keyword,
            "created", article_input.created_at.isoformat(),
        )

        status_mgr  = StatusManager(aid, self._on_status)
        artifact_mgr = ArtifactManager(aid, title=article_input.article_title)

        # Сохраняем входные данные
        artifact_mgr.save("article_input", article_input.to_dict())

        try:
            result = self._execute(article_input, status_mgr, artifact_mgr)
            return result
        except StopIteration:
            status_mgr.set_article_status(STATUS_STOPPED)
            artifact_mgr.update_status(STATUS_STOPPED)
            self._log("Пайплайн остановлен пользователем")
            return PipelineResult("stopped", aid, final_status=STATUS_STOPPED)
        except Exception as e:
            status_mgr.set_article_status(STATUS_FAILED)
            artifact_mgr.update_status(STATUS_FAILED)
            self._log(f"ОШИБКА: {e}")
            logger.exception(e)
            return PipelineResult("failed", aid, error=str(e))

    def _check_stop(self):
        if self._stopped():
            raise StopIteration("stopped_by_user")

    # ─── Выполнение шагов ─────────────────────────────────────────────────────

    def _execute(self, article_input: ArticleInput,
                 sm: StatusManager, am: ArtifactManager) -> PipelineResult:
        aid = article_input.article_id

        # ── Шаг 1: SERP-анализ ────────────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("serp_analysis", "running")
        step_id = am.log_step_start("serp_analysis")
        self._log("Шаг 1/11: SERP-анализ...")

        serp_bundle = None

        # Если есть путь к файлу — загружаем из него
        if article_input.serp_json_path:
            self._log(f"SERP: загрузка из файла {article_input.serp_json_path}")
            serp_bundle = load_from_file(article_input.serp_json_path)
        else:
            # Пробуем кеш
            self._log("SERP: поиск в кеше...")
            serp_bundle = load_from_cache(
                article_input.main_keyword,
                article_input.language,
                article_input.geo,
            )
            if serp_bundle:
                self._log(f"SERP: найден кеш ({len(serp_bundle.pages)} страниц)")
            else:
                raise ValueError(
                    "Нет SERP данных. Загрузите JSON файл от краулера."
                )
        am.save("serp_bundle", serp_bundle.to_dict())

        # Подхватываем источники из JSON если они были переданы
        manual_sources = getattr(serp_bundle, '_manual_sources', None)
        if manual_sources:
            article_input.manual_sources = manual_sources
            self._log(f"SERP: загружено {len(manual_sources)} источников")

        am.log_step_finish(step_id)
        sm.set_step_status("serp_analysis", "done")
        sm.set_article_status(STATUS_SERP_DONE)

        # ── Шаг 2: Анализ конкурентов ─────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("competitor_analysis", "running")
        step_id = am.log_step_start("competitor_analysis")
        self._log("Шаг 2/11: Анализ конкурентов (Claude)...")

        cached = agent_cache.get("competitor_analysis_agent", article_input)
        if cached is not None:
            self._log("Кеш-хит — пропускаем LLM-вызов")
            competitor_report = CompetitorAnalysisReport.model_validate(cached)
        else:
            competitor_report = self.competitor_agent.run(article_input, serp_bundle)
            agent_cache.save("competitor_analysis_agent", article_input, competitor_report.to_dict())
            self._save_prompt("competitor_analysis", self.competitor_agent)
            am.save_prompt("competitor_analysis",
                           self.competitor_agent.last_prompt,
                           self.competitor_agent.last_response)
        am.save("competitor_analysis_report", competitor_report.to_dict())
        am.log_step_finish(step_id)
        sm.set_step_status("competitor_analysis", "done")
        sm.set_article_status(STATUS_COMPETITOR_DONE)

        # ── Шаг 2.5: LSI-слова ────────────────────────────────────────────────
        # Между competitor и brief — извлекаем тематический словарь
        # из SERP-выжимки. Дальше попадает в Brief (lsi_keywords),
        # оттуда в Writer и в QA-метрику.
        self._check_stop()
        self._log("Шаг 3/11: Извлечение LSI-слов...")
        cached = agent_cache.get("lsi_agent", article_input)
        if cached is not None:
            self._log("Кеш-хит — пропускаем LLM-вызов")
            lsi_keywords = cached.get("lsi_keywords", []) if isinstance(cached, dict) else []
        else:
            lsi_keywords = self.lsi_agent.run(article_input, competitor_report)
            agent_cache.save("lsi_agent", article_input, {"lsi_keywords": lsi_keywords})

        # ── Шаг 3: Формирование ТЗ ────────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("brief_generation", "running")
        step_id = am.log_step_start("brief_generation")
        self._log("Шаг 4/11: Формирование ТЗ (Claude)...")

        cached = agent_cache.get("brief_agent", article_input)
        if cached is not None:
            self._log("Кеш-хит — пропускаем LLM-вызов")
            brief = Brief.model_validate(cached)
        else:
            brief = self.brief_agent.run(article_input, competitor_report)
            agent_cache.save("brief_agent", article_input, brief.to_dict())
            self._save_prompt("brief_generation", self.brief_agent)
            am.save_prompt("brief_generation",
                           self.brief_agent.last_prompt,
                           self.brief_agent.last_response)
        # Подмешиваем LSI в Brief — кэш сохранил Brief без LSI, добавляем
        # после загрузки, чтобы LSI всегда был свежим из своего кэша.
        brief.lsi_keywords = lsi_keywords
        am.save("brief", brief.to_dict())
        am.log_step_finish(step_id)
        sm.set_step_status("brief_generation", "done")
        sm.set_article_status(STATUS_BRIEF_DONE)

        # ── Шаг 4: Структура статьи ───────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("outline_generation", "running")
        step_id = am.log_step_start("outline_generation")
        self._log("Шаг 5/11: Структура статьи (Claude)...")

        cached = agent_cache.get("outline_agent", article_input)
        if cached is not None:
            self._log("Кеш-хит — пропускаем LLM-вызов")
            outline = Outline.model_validate(cached)
        else:
            outline = self.outline_agent.run(article_input, competitor_report, brief)
            agent_cache.save("outline_agent", article_input, outline.to_dict())
            self._save_prompt("outline_generation", self.outline_agent)
            am.save_prompt("outline_generation",
                           self.outline_agent.last_prompt,
                           self.outline_agent.last_response)
        am.save("outline", outline.to_dict())
        am.log_step_finish(step_id)
        sm.set_step_status("outline_generation", "done")
        sm.set_article_status(STATUS_OUTLINE_DONE)

        # ── Пауза для ревью outline пользователем ─────────────────────────────
        if self._on_review_ready:
            import json as _json

            # Автоподбор архетипа по нише сайта и интенту.
            # Ниша берётся из БД по site_domain; если не задана — None.
            suggested_archetype_id = None
            suggested_archetype_info = None
            niche_id = None
            site = None
            try:
                from app.storage.repositories import get_site, get_archetype
                from app.services.archetype_matcher import suggest_archetype
                site = get_site(article_input.site_domain)
                niche_id = site.get("niche_id") if site else None
                if niche_id:
                    suggested_archetype_id = suggest_archetype(
                        article_input.article_title,
                        niche_id,
                        article_input.intent,
                        llm_client=self.llm,
                    )
                    if suggested_archetype_id:
                        arch = get_archetype(suggested_archetype_id)
                        if arch:
                            suggested_archetype_info = {
                                "archetype_id": arch["archetype_id"],
                                "name_ru":      arch["name_ru"],
                                "description":  arch.get("description"),
                            }
                            self._log(
                                f"Предложенный архетип: {arch['name_ru']} "
                                f"({arch['archetype_id']})"
                            )
                else:
                    self._log("Архетип не подобран: у сайта не задана ниша")
            except Exception as e:
                logger.warning(f"Автоподбор архетипа не сработал: {e}")

            # Собираем данные для панели ревью
            review_data = {
                "competitor": {
                    "word_count_per_page":  competitor_report.word_count_range.per_page,
                    "word_count_avg":       int(competitor_report.word_count_range.avg),
                    "word_count_min":       competitor_report.word_count_range.min,
                    "word_count_max":       competitor_report.word_count_range.max,
                    "h2_per_page":          competitor_report.h2_count_range.per_page,
                    "h2_avg":               round(competitor_report.h2_count_range.avg, 1),
                    "h2_min":               competitor_report.h2_count_range.min,
                    "h2_max":               competitor_report.h2_count_range.max,
                    "common_h2_titles":     [
                        {"title": t.title, "frequency": t.frequency}
                        for t in competitor_report.common_h2_titles
                    ],
                    "must_have_topics":     competitor_report.must_have_topics,
                    "content_gaps":         [
                        g.model_dump() if hasattr(g, 'model_dump') else g
                        for g in competitor_report.content_gaps
                    ],
                },
                "outline": {
                    "h1":       outline.h1,
                    "sections": [
                        {
                            "section_id":        s.section_id,
                            "title":             s.title,
                            "level":             s.level,
                            "target_word_count": s.target_word_count,
                            "purpose":           s.purpose,
                            "keywords":          s.keywords,
                            "must_cover":        s.must_cover,
                        }
                        for s in outline.sections
                    ],
                },
                "archetype": {
                    "suggested_id":   suggested_archetype_id,
                    "suggested_info": suggested_archetype_info,
                    "niche_id":       niche_id,
                    "alternatives":   self._get_archetype_alternatives(niche_id),
                },
            }

            self._log("__REVIEW_READY__:" + _json.dumps(review_data, ensure_ascii=False))
            self._on_review_ready(review_data)

            # Ждём пока пользователь подтвердит или изменит outline
            self._log("⏸ Ожидание подтверждения структуры...")
            self._pause_event.clear()
            try:
                self._pause_event.wait()
            finally:
                self._pause_event.set()  # гарантируем разблокировку в любом случае

            # Проверяем не был ли нажат Stop во время паузы
            self._check_stop()

            # Применяем изменения пользователя если они есть
            if self._reviewed_outline:
                from app.schemas.outline import SectionSpec, FaqSection
                new_sections = []
                for s in self._reviewed_outline.get("sections", []):
                    new_sections.append(SectionSpec(
                        section_id        = s.get("section_id", ""),
                        title             = s.get("title", ""),
                        level             = s.get("level", "H2"),
                        target_word_count = int(s.get("target_word_count", 200)),
                        purpose           = s.get("purpose", ""),
                        keywords          = s.get("keywords", []),
                        must_cover        = s.get("must_cover", []),
                    ))
                outline.sections = new_sections
                self._log(f"✓ Структура обновлена пользователем: {len(new_sections)} секций")

            # Финальный выбор архетипа: либо то, что вернул юзер из UI,
            # либо предложенный системой. Логируем в archetype_picks.
            chosen_archetype_id = None
            if self._reviewed_outline:
                chosen_archetype_id = self._reviewed_outline.get("chosen_archetype_id")
            if not chosen_archetype_id:
                chosen_archetype_id = suggested_archetype_id

            if chosen_archetype_id:
                try:
                    from app.storage.repositories import (
                        log_archetype_pick, get_connection, release_connection
                    )
                    # Лог в archetype_picks (matched вычислится автоматом)
                    log_archetype_pick(
                        article_id              = aid,
                        suggested_archetype_id  = suggested_archetype_id,
                        chosen_archetype_id     = chosen_archetype_id,
                        niche_id                = niche_id,
                        intent                  = article_input.intent,
                    )
                    # Записываем выбранный архетип в саму статью
                    conn = get_connection()
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE articles SET archetype_id=%s WHERE article_id=%s",
                                (chosen_archetype_id, aid),
                            )
                        conn.commit()
                    finally:
                        release_connection(conn)
                    self._log(
                        f"Архетип статьи: {chosen_archetype_id}"
                        + (" (предложение принято)" if chosen_archetype_id == suggested_archetype_id
                           else f" (изменён с {suggested_archetype_id})")
                    )
                except Exception as e:
                    logger.warning(f"Не удалось записать выбор архетипа: {e}")

        # Передаём финальный список секций в GUI
        if self._on_log:
            import json as _json
            sec_titles = [s.title for s in outline.sections]
            self._on_log(f"__SECTIONS_PLAN__:{_json.dumps(sec_titles, ensure_ascii=False)}")

        # ── Шаг 5: Section pipeline ───────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("section_pipeline", "running")
        step_id = am.log_step_start("section_pipeline")
        sm.set_article_status(STATUS_SECTIONS_PROGRESS)

        final_sections: dict[str, str] = {}
        # Резюме уже написанных секций (заголовок -> суть) для сквозной связности.
        # Передаётся писателю, чтобы он не повторялся и делал плавные переходы.
        section_summaries: dict[str, str] = {}
        weak_sections:  list[str]      = []

        # Достаём профиль автора один раз перед циклом секций.
        # Передаётся в Writer чтобы он писал от лица этого человека.
        author = None
        if article_input.author_id:
            try:
                from app.storage.repositories import get_author
                author = get_author(article_input.author_id)
            except Exception as e:
                logger.warning(f"Не удалось загрузить автора: {e}")

        for i, spec in enumerate(outline.sections):
            self._check_stop()
            self._log(f"Шаг 6/11: Секция {i+1}/{len(outline.sections)}: '{spec.title}'")
            sm.set_step_status(f"section_{spec.section_id}", "running")

            result = run_section(
                spec              = spec,
                article_input     = article_input,
                brief             = brief,
                competitor_report = competitor_report,
                previous_sections = dict(section_summaries),
                writer            = self.writer_agent,
                critic            = self.critic_agent,
                editor            = self.editor_agent,
                artifact_mgr      = am,
                always_review     = article_input.always_review_sections,
                stop_flag         = self._stopped,
                progress_cb       = self._log,
                prompt_cb         = self._on_prompt,
                serp_urls         = serp_bundle.urls,
                manual_sources    = getattr(article_input, 'manual_sources', None),
                author            = author,
            )

            final_sections[spec.section_id] = result.final_text
            # Резюме секции (с цифрами и фактами) попадёт в промпт Writer'у
            # следующей секции — чтобы он не противоречил уже написанному.
            # Если резюме не получено (маркер отсутствует) — fallback на заголовок.
            section_summaries[spec.title] = result.summary or spec.title
            if result.is_weak:
                weak_sections.append(spec.section_id)

            sm.set_step_status(
                f"section_{spec.section_id}",
                "weak" if result.is_weak else "done"
            )

        am.log_step_finish(step_id)
        sm.set_step_status("section_pipeline", "done")

        # ── Шаг 6: Сборка статьи ─────────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("full_draft_assembly", "running")
        step_id = am.log_step_start("full_draft_assembly")
        self._log("Шаг 7/11: Сборка статьи...")

        full_draft = assemble_draft(outline, final_sections)
        am.save("full_draft", full_draft.to_dict())
        am.save_markdown(full_draft.content_markdown)
        am.log_step_finish(step_id)
        sm.set_step_status("full_draft_assembly", "done")
        sm.set_article_status(STATUS_DRAFT_READY)

        # ── Шаг 6.5: Поиск и вставка картинок ─────────────────────────────────
        self._check_stop()
        try:
            self._log("Шаг 8/11: Поиск картинок...")
            from app.agents.image_finder_agent import ImageFinderAgent
            img_agent = ImageFinderAgent(self.llm)
            from app.storage.file_storage import article_dir as _article_dir_path
            md_with_images = img_agent.run(
                markdown=full_draft.content_markdown,
                main_topic=article_input.article_title,
                main_keyword=article_input.main_keyword,
                article_dir=_article_dir_path(aid, article_input.article_title),
                language=article_input.language or "ru",
            )
            if md_with_images != full_draft.content_markdown:
                full_draft.content_markdown = md_with_images
                am.save("full_draft", full_draft.to_dict())
                am.save_markdown(md_with_images)
                self._log("Картинки добавлены в статью")
            else:
                self._log("Картинки не найдены — статья без изображений")
        except Exception as e:
            logger.warning(f"Шаг картинок упал, продолжаем без них: {e}")

        # ── Шаг 6.7: FAQ (если outline.faq_section.enabled) ───────────────────
        # Отдельный агент пишет блок FAQ по вопросам из outline.faq_section.
        # Вставляем FAQ перед секцией «Заключение» (fallback — перед последней
        # секцией; если и её нет — в конец).
        self._check_stop()
        try:
            # Если Writer уже написал FAQ как обычную секцию (Claude иногда так делает,
            # ориентируясь на required_elements=faq в брифе) — faq_writer_agent НЕ запускаем.
            has_faq_in_sections = any(
                "faq" in s.section_id.lower() or "faq" in s.title.lower()
                for s in outline.sections
            )
            if (outline.faq_section.enabled
                    and outline.faq_section.questions
                    and not has_faq_in_sections):
                self._log("Шаг 9/11: Генерация FAQ...")
                from app.agents.faq_writer_agent import FAQWriterAgent
                faq_agent = FAQWriterAgent(self.llm)
                # Автор берётся из БД по article_input.author_id
                author = None
                if article_input.author_id:
                    try:
                        from app.storage.repositories import get_author
                        author = get_author(article_input.author_id)
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить автора для FAQ: {e}")
                faq_md = faq_agent.run_with_questions(
                    article_input=article_input,
                    brief=brief,
                    article_markdown=full_draft.content_markdown,
                    questions=outline.faq_section.questions,
                    author=author,
                )
                if faq_md:
                    # Вставляем перед «Заключением» / «Conclusion» / «Итог».
                    # Если такой секции нет — в конец статьи.
                    md = full_draft.content_markdown
                    import re as _re
                    m = _re.search(
                        r"^##\s+(заключен|итог|подводя|conclusion)",
                        md,
                        flags=_re.IGNORECASE | _re.MULTILINE,
                    )
                    if m:
                        md = md[:m.start()] + faq_md.rstrip() + "\n\n" + md[m.start():]
                    else:
                        md = md.rstrip() + "\n\n" + faq_md.rstrip() + "\n"
                    full_draft.content_markdown = md
                    am.save("full_draft", full_draft.to_dict())
                    am.save_markdown(md)
                    am.save_prompt("faq_writer",
                                   faq_agent.last_prompt,
                                   faq_agent.last_response)
                    self._log(f"FAQ добавлен ({len(outline.faq_section.questions)} вопросов)")
                else:
                    self._log("FAQ не сгенерирован — пропускаем")
            elif has_faq_in_sections:
                self._log("Шаг 9/11: FAQ уже в outline.sections — пропускаем отдельный шаг")
        except Exception as e:
            logger.warning(f"Шаг FAQ упал, продолжаем без него: {e}")

        # ── Шаг 7: Финальный QA ───────────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("final_qa", "running")
        step_id = am.log_step_start("final_qa")
        self._log("Шаг 10/11: Финальный QA (Claude)...")

        qa_result = self.qa_agent.run(article_input, brief, competitor_report, full_draft)
        am.save("qa_result", qa_result.to_dict())
        self._save_prompt("final_qa", self.qa_agent)
        am.save_prompt("final_qa",
                       self.qa_agent.last_prompt,
                       self.qa_agent.last_response)
        am.update_qa(qa_result.status, qa_result.score)
        am.log_step_finish(step_id)
        sm.set_step_status("final_qa", "done")
        sm.set_article_status(STATUS_QA_DONE)

        # ── Шаг 8: Метаданные ─────────────────────────────────────────────────
        self._check_stop()
        sm.set_step_status("metadata_generation", "running")
        step_id = am.log_step_start("metadata_generation")
        self._log("Шаг 11/11: Метаданные (Claude)...")

        final_package = self.metadata_agent.run(
            article_input, brief, full_draft, qa_result
        )
        final_package.article_id = aid  # нужен для нахождения папки статьи
        am.save("final_package", final_package.to_dict())
        self._save_prompt("metadata_generation", self.metadata_agent)
        am.save_prompt("metadata_generation",
                       self.metadata_agent.last_prompt,
                       self.metadata_agent.last_response)
        am.log_step_finish(step_id)
        sm.set_step_status("metadata_generation", "done")

        # ── Шаг 9: Финальный статус ───────────────────────────────────────────
        final_status = sm.get_final_article_status(qa_result.status)
        sm.set_article_status(final_status)
        sm.set_step_status("save_results", "done")
        self._log(f"Завершено. Статус: {final_status} | Score: {qa_result.score}")

        return PipelineResult(
            status       = "success",
            article_id   = aid,
            final_status = final_status,
            qa_score     = qa_result.score,
        )
