"""
Главное окно приложения.

Весь UI реализован через QWebEngineView + QWebChannel.
Python отвечает только за:
  - запуск пайплайна в QThread
  - передачу событий (лог, статус, диалог агентов, результат) в JS
  - открытие файлов/папок через нативные диалоги
  - чтение БД и файлов статей
"""
import json
import os
import subprocess
import sys

from PySide6.QtCore    import Qt, QThread, Signal, QObject, Slot, QUrl, QTimer
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QFileDialog, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore    import QWebEnginePage
from PySide6.QtGui              import QDesktopServices
from PySide6.QtCore             import QUrl as _QUrl_for_links
from PySide6.QtWebEngineCore    import QWebEngineSettings
from PySide6.QtWebChannel       import QWebChannel

from app.orchestrator.pipeline_orchestrator import PipelineOrchestrator
from app.schemas.article_input  import ArticleInput
from app.services.input_normalizer import normalize
from app.services.serp_cache    import has_cache
from app.services.cost_tracker  import cost_tracker
from app.storage.repositories   import get_all_articles
from app.storage.file_storage   import article_dir
from app.config.settings        import ARTICLES_DIR


# ─── Pipeline worker (без изменений по логике) ───────────────────────────────

class PipelineWorker(QObject):
    log_signal    = Signal(str)
    status_signal = Signal(str, str)
    prompt_signal = Signal(str, str, str)
    review_signal = Signal(dict)   # данные для панели ревью
    done_signal   = Signal(dict)
    error_signal  = Signal(str)

    def __init__(self, article_input: ArticleInput):
        super().__init__()
        self.article_input = article_input
        self._orchestrator: PipelineOrchestrator | None = None

    def run(self):
        self._orchestrator = PipelineOrchestrator(
            on_status       = lambda step, st: self.status_signal.emit(step, st),
            on_log          = lambda msg:      self.log_signal.emit(msg),
            on_prompt       = lambda s, p, r:  self.prompt_signal.emit(s, p, r),
            on_review_ready = lambda data:     self.review_signal.emit(data),
        )
        try:
            result = self._orchestrator.run_pipeline(self.article_input)
            self.done_signal.emit({
                "status":       result.status,
                "article_id":   result.article_id,
                "final_status": result.final_status,
                "qa_score":     result.qa_score,
                "error":        result.error,
            })
        except Exception as e:
            self.error_signal.emit(str(e))

    def stop(self):
        if self._orchestrator:
            self._orchestrator.stop()

    def resume_with_outline(self, outline_data: dict):
        if self._orchestrator:
            self._orchestrator.resume_with_outline(outline_data)


class CostBridge(QObject):
    """Живёт в главном потоке. Qt доставляет emit() из других потоков
    через queued connection автоматически."""
    cost_signal = Signal(float, float, float, float)  # article, session, last_call, total


# ─── JS ↔ Python мост ────────────────────────────────────────────────────────

class AppBridge(QObject):
    """
    Все методы доступны из JS как window.bridge.<method>().
    """

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self._win = window

    # ── Форма ──────────────────────────────────────────────────────────────────

    @Slot(str)
    def runPipeline(self, json_str: str):
        """JS передаёт данные формы → запускаем пайплайн."""
        try:
            raw = json.loads(json_str)
        except Exception:
            return
        self._win._on_run_requested(raw)

    @Slot(str)
    def validateForm(self, json_str: str):
        try:
            raw = json.loads(json_str)
        except Exception:
            return
        self._win._on_validate_requested(raw)

    @Slot()
    def browseSerp(self):
        import logging
        logging.getLogger(__name__).info("[browseSerp] slot called")
        self._win._on_browse_serp()

    @Slot()
    def onClearSerp(self):
        self._win._serp_path = None

    @Slot(str)
    def copyToClipboard(self, text: str):
        """Копирует текст в системный буфер через Qt."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    @Slot(result=str)
    def getSites(self) -> str:
        """
        Возвращает список сайтов из БД в виде JSON-строки.
        JS использует это для наполнения dropdown в форме новой статьи.
        Формат: [{"domain": "...", "name": "...", "is_test": true/false}, ...]
        """
        try:
            from app.storage.repositories import get_all_sites
            sites = get_all_sites(include_test=True)
            payload = [
                {"domain": s["domain"], "name": s["name"], "is_test": s["is_test"]}
                for s in sites
            ]
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getSites] failed: {e}")
            return "[]"

    @Slot(result=str)
    def getSitesWithCounts(self) -> str:
        """
        Расширенный список сайтов для страницы «Сайты»: с именем ниши
        и количеством статей. Используется в карточках.
        """
        try:
            from app.storage.repositories import (
                get_all_sites, count_articles_for_site,
                count_authors_for_site, get_niche
            )
            sites = get_all_sites(include_test=True)
            payload = []
            for s in sites:
                niche_name = None
                if s.get("niche_id"):
                    n = get_niche(s["niche_id"])
                    if n:
                        niche_name = n["name_ru"]
                payload.append({
                    "domain":        s["domain"],
                    "name":          s["name"],
                    "is_test":       s["is_test"],
                    "niche_id":      s.get("niche_id"),
                    "niche_name":    niche_name,
                    "article_count": count_articles_for_site(s["domain"]),
                    "author_count":  count_authors_for_site(s["domain"], only_active=False),
                })
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getSitesWithCounts] failed: {e}")
            return "[]"
        
    @Slot(bool, result=str)
    def getAnalyticsData(self, include_test: bool) -> str:
        """
        Возвращает агрегированные данные для страницы аналитики:
        summary (общие цифры) + три массива (sites, niches, archetypes).
        Все агрегации делаются одним проходом по таблице articles.
        """
        try:
            from app.storage.db_manager import get_connection, release_connection
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    # Фильтр по тестовым сайтам
                    test_filter = "" if include_test else \
                        "JOIN sites s ON a.site_domain = s.domain AND s.is_test = FALSE"
                    base_join = "FROM articles a " + (
                        test_filter if test_filter else
                        "JOIN sites s ON a.site_domain = s.domain"
                    )

                    # Общая сводка
                    cur.execute(f"""
                        SELECT COUNT(*),
                               COALESCE(AVG(NULLIF(a.qa_score, 0))::int, 0),
                               COALESCE(SUM(a.cost_usd), 0),
                               COALESCE(AVG(NULLIF(a.cost_usd, 0)), 0)
                        {base_join}
                    """)
                    total_articles, avg_qa, total_cost, avg_cost = cur.fetchone()

                    # По сайтам
                    cur.execute(f"""
                        SELECT a.site_domain, s.is_test,
                               COUNT(*) AS cnt,
                               COALESCE(AVG(NULLIF(a.qa_score, 0))::int, 0) AS avg_qa,
                               COALESCE(SUM(a.cost_usd), 0) AS total_cost,
                               COALESCE(AVG(NULLIF(a.cost_usd, 0)), 0) AS avg_cost
                        {base_join}
                        GROUP BY a.site_domain, s.is_test
                        ORDER BY cnt DESC
                    """)
                    sites = [
                        {"domain": r[0], "is_test": r[1], "count": r[2],
                         "avg_qa": r[3], "total_cost": float(r[4]),
                         "avg_cost": float(r[5])}
                        for r in cur.fetchall()
                    ]

                    # По нишам (через site.niche_id)
                    cur.execute(f"""
                        SELECT COALESCE(n.name_ru, '— без ниши —'),
                               COUNT(*) AS cnt,
                               COALESCE(AVG(NULLIF(a.qa_score, 0))::int, 0) AS avg_qa,
                               COALESCE(AVG(NULLIF(a.cost_usd, 0)), 0) AS avg_cost
                        {base_join}
                        LEFT JOIN niches n ON s.niche_id = n.niche_id
                        GROUP BY n.name_ru
                        ORDER BY cnt DESC
                    """)
                    niches = [
                        {"name": r[0], "count": r[1], "avg_qa": r[2],
                         "avg_cost": float(r[3])}
                        for r in cur.fetchall()
                    ]

                    # По архетипам — отдельно считаем совпадение с предложением
                    cur.execute(f"""
                        SELECT COALESCE(ar.name_ru, '— не задан —') AS arch_name,
                               COUNT(*) AS cnt,
                               COALESCE(AVG(NULLIF(a.qa_score, 0))::int, 0) AS avg_qa
                        {base_join}
                        LEFT JOIN archetypes ar ON a.archetype_id = ar.archetype_id
                        GROUP BY ar.name_ru
                        ORDER BY cnt DESC
                    """)
                    archetypes_raw = [
                        {"name": r[0], "count": r[1], "avg_qa": r[2]}
                        for r in cur.fetchall()
                    ]

                    # Подмешиваем процент совпадений с предложенным архетипом
                    cur.execute(f"""
                        SELECT COALESCE(ar.name_ru, '— не задан —'),
                               COUNT(*) FILTER (WHERE p.matched = TRUE)::float
                                 / NULLIF(COUNT(*), 0) * 100
                        FROM archetype_picks p
                        JOIN articles a ON p.article_id = a.article_id
                        JOIN sites s ON a.site_domain = s.domain
                        LEFT JOIN archetypes ar ON p.chosen_archetype_id = ar.archetype_id
                        {"" if include_test else "WHERE s.is_test = FALSE"}
                        GROUP BY ar.name_ru
                    """)
                    match_map = {r[0]: round(r[1] or 0, 1) for r in cur.fetchall()}
                    for a in archetypes_raw:
                        a["match_pct"] = match_map.get(a["name"], 0)

                    payload = {
                        "summary": {
                            "total_articles": total_articles,
                            "avg_qa":         avg_qa,
                            "total_cost":     float(total_cost),
                            "avg_cost":       float(avg_cost),
                        },
                        "sites":      sites,
                        "niches":     niches,
                        "archetypes": archetypes_raw,
                    }
                    return json.dumps(payload, ensure_ascii=False)
            finally:
                release_connection(conn)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getAnalyticsData] failed: {e}")
            return json.dumps({"error": str(e)})

    @Slot(result=str)
    def getNiches(self) -> str:
        """Возвращает справочник ниш для dropdown."""
        try:
            from app.storage.repositories import get_all_niches
            niches = get_all_niches()
            payload = [
                {"niche_id": n["niche_id"], "name_ru": n["name_ru"]}
                for n in niches
            ]
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getNiches] failed: {e}")
            return "[]"

    @Slot(str, result=str)
    def createSite(self, payload_json: str) -> str:
        """
        Создаёт сайт из JSON {domain, name, niche_id, is_test}.
        Возвращает {ok: bool, error?: str}.
        """
        import logging
        log = logging.getLogger(__name__)
        try:
            data = json.loads(payload_json)
            domain = (data.get("domain") or "").strip()
            name = (data.get("name") or "").strip()
            niche_id = data.get("niche_id") or None
            is_test = bool(data.get("is_test"))
            if not domain or not name:
                return json.dumps({"ok": False, "error": "Домен и имя обязательны"})

            from app.storage.repositories import create_site, get_site
            if get_site(domain):
                return json.dumps({"ok": False, "error": f"Сайт {domain} уже существует"})

            create_site(domain=domain, name=name, niche_id=niche_id, is_test=is_test)
            log.info(f"[createSite] created: {domain}")
            return json.dumps({"ok": True})
        except Exception as e:
            log.error(f"[createSite] failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def getAuthorsForSite(self, domain: str) -> str:
        """Возвращает всех авторов сайта (включая неактивных)."""
        try:
            from app.storage.repositories import get_authors_for_site
            authors = get_authors_for_site(domain, only_active=False)
            payload = [
                {
                    "author_id":  a["author_id"],
                    "name":       a["name"],
                    "character":  a.get("character"),
                    "tone":       a.get("tone"),
                    "age_image":  a.get("age_image"),
                    "is_active":  a["is_active"],
                }
                for a in authors
            ]
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getAuthorsForSite] failed: {e}")
            return "[]"

    @Slot(str, result=str)
    def getStyleReferences(self, niche_id: str) -> str:
        """
        Возвращает список писателей-референсов, подходящих под нишу сайта.
        Универсальные референсы (без niche_tags или с пустым массивом) включаются всегда.
        """
        try:
            from app.storage.repositories import get_all_style_references
            refs = get_all_style_references(
                language="ru",
                niche=niche_id or None,
                only_active=True,
            )
            payload = [
                {
                    "reference_id":     r["reference_id"],
                    "name":             r["name"],
                    "notes":            r.get("notes"),
                    "has_extracted":    bool(r.get("extracted_style")),
                }
                for r in refs
            ]
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getStyleReferences] failed: {e}")
            return "[]"

    @Slot(str, result=str)
    def extractStyleForReference(self, reference_id: str) -> str:
        """
        Возвращает {character, tone, age_image} для писателя-референса.
        Если в БД уже есть extracted_style — берёт из кэша.
        Если нет — вызывает агента, сохраняет, возвращает.
        """
        import logging
        log = logging.getLogger(__name__)
        try:
            from app.storage.repositories import (
                get_style_reference, save_extracted_style
            )
            ref = get_style_reference(reference_id)
            if not ref:
                return json.dumps({"ok": False, "error": "Референс не найден"})

            # Если уже извлекали — возвращаем из кэша
            cached = ref.get("extracted_style")
            if cached:
                log.info(f"[extractStyle] кэш для {reference_id}")
                return json.dumps({
                    "ok": True,
                    "character": cached,
                    "tone":      ref.get("extracted_tone") or "",
                    "age_image": ref.get("extracted_age_image") or "",
                })

            # Иначе — вызываем агента
            log.info(f"[extractStyle] нет кэша для {reference_id}, вызываем агента")
            from app.llm.llm_client import LLMClient
            from app.agents.style_extractor_agent import StyleExtractorAgent
            agent = StyleExtractorAgent(LLMClient())
            result = agent.run(ref)
            if not result:
                return json.dumps({"ok": False, "error": "Не удалось извлечь стиль"})

            save_extracted_style(
                reference_id,
                character = result["character"],
                tone      = result.get("tone", ""),
                age_image = result.get("age_image", ""),
            )
            return json.dumps({
                "ok": True,
                "character": result["character"],
                "tone":      result.get("tone", ""),
                "age_image": result.get("age_image", ""),
            })
        except Exception as e:
            log.error(f"[extractStyleForReference] failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def getAuthorsInNiche(self, niche_id: str) -> str:
        """
        Возвращает авторов из ниши (для «создать по образцу»).
        Используется в модалке создания автора.
        """
        try:
            from app.storage.repositories import get_authors_in_niche
            authors = get_authors_in_niche(niche_id)
            payload = [
                {
                    "author_id":   a["author_id"],
                    "name":        a["name"],
                    "site_domain": a["site_domain"],
                    "character":   a.get("character"),
                    "tone":        a.get("tone"),
                    "age_image":   a.get("age_image"),
                }
                for a in authors
            ]
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[getAuthorsInNiche] failed: {e}")
            return "[]"

    @Slot(str, result=str)
    def createAuthor(self, payload_json: str) -> str:
        """
        Создаёт автора из JSON {site_domain, name, character, tone, age_image}.
        author_id генерируется автоматически. niche_id наследуется от сайта.
        """
        import logging
        log = logging.getLogger(__name__)
        try:
            import uuid
            data = json.loads(payload_json)
            site_domain = (data.get("site_domain") or "").strip()
            name = (data.get("name") or "").strip()
            if not site_domain or not name:
                return json.dumps({"ok": False, "error": "Сайт и имя обязательны"})

            from app.storage.repositories import (
                create_author, get_site
            )
            site = get_site(site_domain)
            if not site:
                return json.dumps({"ok": False, "error": f"Сайт {site_domain} не найден"})

            author_id = str(uuid.uuid4())
            create_author(
                author_id=author_id,
                site_domain=site_domain,
                name=name,
                character=data.get("character") or None,
                tone=data.get("tone") or None,
                age_image=data.get("age_image") or None,
                niche_id=site.get("niche_id"),
                reference_id=data.get("reference_id") or None,
                is_active=True,
            )
            log.info(f"[createAuthor] created: {name} ({author_id}) for {site_domain}")
            return json.dumps({"ok": True})
        except Exception as e:
            log.error(f"[createAuthor] failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, bool, result=str)
    def setAuthorActive(self, author_id: str, is_active: bool) -> str:
        try:
            from app.storage.repositories import set_author_active
            set_author_active(author_id, is_active)
            return json.dumps({"ok": True})
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[setAuthorActive] failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, str)
    def loadSerpFromContent(self, filename: str, content: str):
        """Drag & drop: получаем содержимое файла из JS, сохраняем во временный файл."""
        import tempfile, logging
        log = logging.getLogger(__name__)
        try:
            raw = json.loads(content)
            # Сохраняем во временный файл чтобы пайплайн мог его прочитать
            tmp = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False,
                encoding='utf-8', prefix='serp_'
            )
            json.dump(raw, tmp, ensure_ascii=False)
            tmp.close()
            self._win._serp_path = tmp.name
            size_kb = round(len(content.encode()) / 1024, 1)
            count   = len(raw) if isinstance(raw, list) else len(raw.keys())
            secondary = raw.get("secondary_keywords", []) if isinstance(raw, dict) else []
            log.info(f"[loadSerpFromContent] saved to {tmp.name}")
            self._win._js(
                f"serpLoaded({json.dumps(filename)}, {count}, {size_kb}, "
                f"{json.dumps(secondary)});"
            )
        except Exception as e:
            log.error(f"[loadSerpFromContent] error: {e}")
            self._win._js(f"alert('Ошибка загрузки SERP: {str(e)[:80]}');")

    @Slot()
    def stopPipeline(self):
        self._win._on_stop_clicked()

    @Slot(str)
    def resumePipeline(self, outline_json: str):
        """Вызывается из JS после того как пользователь подтвердил/изменил outline."""
        try:
            outline_data = json.loads(outline_json)
        except Exception:
            outline_data = {}
        self._win._on_resume_pipeline(outline_data)

    # ── История / статьи ───────────────────────────────────────────────────────

    @Slot(result=str)
    def getArticles(self) -> str:
        """Возвращает JSON-список всех статей из БД."""
        import logging
        log = logging.getLogger(__name__)
        try:
            articles = get_all_articles()
            safe = []
            for a in articles:
                safe.append({k: (str(v) if v is not None else None)
                             for k, v in a.items()})
            result = json.dumps(safe, ensure_ascii=False)
            log.info(f"[getArticles] returning {len(safe)} articles")
            return result
        except Exception as e:
            log.error(f"[getArticles] error: {e}")
            return json.dumps([])

    @Slot(str, result=str)
    def getArticleResult(self, article_id: str) -> str:
        """Читает final_package.json + qa_result.json для статьи."""
        import logging
        log = logging.getLogger(__name__)
        try:
            adir = article_dir(article_id)
            log.info(f"[getArticleResult] looking in {adir}")
            fp = adir / "final_package.json"
            qa = adir / "qa_result.json"
            if fp.exists() and qa.exists():
                pkg = json.loads(fp.read_text(encoding="utf-8"))
                qar = json.loads(qa.read_text(encoding="utf-8"))

                # Готовим версию markdown с картинками как data: URI —
                # для отображения в предпросмотре. Оригинал с относительными
                # путями остаётся в pkg.article_markdown (для копирования
                # пользователем и сохранения в WordPress).
                import base64, re as _re
                md_original = pkg.get("article_markdown", "") or ""
                md_preview  = md_original

                def _embed(match):
                    rel = match.group(2)
                    try:
                        img_path = adir / rel
                        if not img_path.exists():
                            return match.group(0)
                        ext = img_path.suffix.lower().lstrip(".") or "webp"
                        mime = "image/webp" if ext == "webp" else f"image/{ext}"
                        b64 = base64.b64encode(img_path.read_bytes()).decode()
                        return f"{match.group(1)}data:{mime};base64,{b64}{match.group(3)}"
                    except Exception:
                        return match.group(0)

                md_preview = _re.sub(
                    r"(!\[[^\]]*\]\()(images/[^)\s]+)(\))",
                    _embed,
                    md_preview,
                )
                pkg["article_markdown_preview"] = md_preview

                return json.dumps(
                    {"pkg": pkg, "qa": qar},
                    ensure_ascii=False,
                )
            else:
                log.warning(f"[getArticleResult] files missing: fp={fp.exists()} qa={qa.exists()}")
        except Exception as e:
            log.error(f"[getArticleResult] error: {e}")
        return "null"

    @Slot(str)
    def openArticleFolder(self, article_id: str):
        self._win._open_article_folder(article_id)

    @Slot()
    def openCurrentFolder(self):
        self._win._open_article_folder(self._win._current_article_id)


# ─── Главное окно ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEO Pipeline — Генератор статей")
        self.resize(1400, 900)

        self._worker: PipelineWorker | None = None
        self._thread: QThread | None = None
        self._current_article_id: str | None = None
        self._serp_path: str | None = None

        # CostBridge живёт в главном потоке — Qt автоматически делает
        # cross-thread emit через queued connection
        self._cost_bridge = CostBridge()
        self._cost_bridge.cost_signal.connect(self._on_cost)

        # Регистрируем коллбэк cost_tracker сразу при старте —
        # чтобы накопленный total из файла отрисовался в UI до запуска пайплайна.
        cost_tracker.set_callback(self._emit_cost)

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── WebEngineView ──────────────────────────────────────────────────────
        self._view = QWebEngineView()

        # Все внешние ссылки (http/https) открываем в системном браузере,
        # а не во встроенном QtWebEngine — иначе из такой страницы потом
        # невозможно вернуться обратно в приложение.
        class _ExternalLinkPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                if nav_type == QWebEnginePage.NavigationTypeLinkClicked:
                    QDesktopServices.openUrl(url)
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

            def javaScriptConsoleMessage(self, level, message, line_number, source_id):
                # Печатаем JS-ошибки в Python-лог с точным номером строки.
                # source_id — путь к скрипту (обычно qrc:/ или сам HTML).
                print(f"[JS console] level={level} line={line_number} msg={message} src={source_id}")
                super().javaScriptConsoleMessage(level, message, line_number, source_id)

        self._view.setPage(_ExternalLinkPage(self._view))
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        # Разрешаем загрузку картинок с file:// в страницу загруженную с qrc:// —
        # иначе QtWebEngine блокирует это по cross-origin policy
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        # ── WebChannel ─────────────────────────────────────────────────────────
        self._bridge  = AppBridge(self)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._view.setHtml(_build_html(), QUrl("qrc:/"))
        # После загрузки страницы — отдаём в UI текущие счётчики
        self._view.loadFinished.connect(lambda ok: self._emit_cost() if ok else None)
        layout.addWidget(self._view)

    # ── JS helpers ────────────────────────────────────────────────────────────

    def _js(self, code: str):
        """Выполнить JS в главном потоке."""
        self._view.page().runJavaScript(code)

    # ── Обработчики от JS ─────────────────────────────────────────────────────

    def _on_run_requested(self, raw: dict):
        raw["serp_json_path"] = self._serp_path
        result = normalize(raw)
        if not result:
            QMessageBox.warning(self, "Ошибки валидации",
                                "Исправьте ошибки:\n\n" + "\n".join(result.errors))
            return

        if not self._serp_path and not has_cache(
            raw.get("main_keyword", ""),
            raw.get("language", "ru"),
            raw.get("geo", "")
        ):
            QMessageBox.warning(self, "Нет SERP данных",
                                "Загрузите JSON файл от краулера.\nКеш не найден.")
            return

        article = result.article_input
        self._current_article_id = article.article_id

        self._js("uiPipelineStarted();")

        self._worker = PipelineWorker(article)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log_signal.connect(self._on_log)
        self._worker.status_signal.connect(self._on_status)
        self._worker.prompt_signal.connect(self._on_prompt)
        self._worker.review_signal.connect(self._on_review_ready)
        self._worker.done_signal.connect(self._on_pipeline_done)
        self._worker.error_signal.connect(self._on_pipeline_error)

        # Коллбэк уже подключён при старте окна. Сбрасываем только счётчик статьи.
        self._emit_cost()

        self._thread.start()

    def _on_validate_requested(self, raw: dict):
        raw["serp_json_path"] = self._serp_path
        result = normalize(raw)
        if result:
            if not self._serp_path:
                if has_cache(raw.get("main_keyword", ""),
                             raw.get("language", "ru"),
                             raw.get("geo", "")):
                    QMessageBox.information(self, "Валидация",
                        "✅ Данные корректны.\n\nSERP файл не загружен, но найден кеш.")
                else:
                    QMessageBox.warning(self, "Нет SERP данных",
                        "Загрузите JSON файл от краулера.")
            else:
                QMessageBox.information(self, "Валидация", "✅ Данные корректны.")
        else:
            QMessageBox.warning(self, "Ошибки валидации",
                                "\n".join(result.errors))

    def _on_browse_serp(self):
        # QFileDialog нельзя открывать синхронно из QWebChannel-слота —
        # откладываем на следующий тик event loop через singleShot
        QTimer.singleShot(0, self._open_serp_dialog)

    def _open_serp_dialog(self):
        import logging
        logging.getLogger(__name__).info("[_open_serp_dialog] opening QFileDialog")
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить SERP JSON", "", "JSON файлы (*.json)"
        )
        if not path:
            return
        self._serp_path = path
        fname = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            size_kb = round(os.path.getsize(path) / 1024, 1)
            count   = len(raw) if isinstance(raw, list) else len(raw.keys())
            secondary = raw.get("secondary_keywords", []) if isinstance(raw, dict) else []
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось прочитать файл:\n{e}")
            return
        self._js(
            f"serpLoaded({json.dumps(fname)}, {count}, {size_kb}, "
            f"{json.dumps(secondary)});"
        )

    def _on_stop_clicked(self):
        if not self._worker:
            return
        reply = QMessageBox.question(
            self, "Остановить?",
            "Пайплайн ещё выполняется.\nВы уверены?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Просим воркер остановиться. Поток догорит в фоне после
        # текущего HTTP-запроса к LLM (до минуты), нам это не мешает.
        self._worker.stop()

        # Отвязываем воркер от UI прямо сейчас — чтобы можно было
        # запустить новый прогон, не дожидаясь догорания старого.
        try:
            self._worker.done_signal.disconnect()
            self._worker.error_signal.disconnect()
            self._worker.log_signal.disconnect()
            self._worker.status_signal.disconnect()
            self._worker.prompt_signal.disconnect()
            self._worker.review_signal.disconnect()
        except Exception:
            pass

        # Помечаем текущую статью cancelled в БД
        try:
            if self._current_article_id:
                from app.storage.db_manager import get_connection, release_connection
                conn = get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE articles SET status=%s, updated_at=NOW() "
                            "WHERE article_id=%s AND status NOT IN ('done','failed','cancelled')",
                            ("cancelled", self._current_article_id),
                        )
                    conn.commit()
                finally:
                    release_connection(conn)
        except Exception as e:
            logger.warning(f"[stop] cancel mark failed: {e}")

        # Перекладываем старый поток в список "догорающих" — Qt запрещает
        # уничтожать живой QThread, поэтому держим ссылку пока он сам не выйдет.
        if not hasattr(self, "_zombie_threads"):
            self._zombie_threads = []
        zombie = (self._thread, self._worker)
        self._zombie_threads.append(zombie)

        def _cleanup_zombie(z=zombie):
            try:
                self._zombie_threads.remove(z)
            except ValueError:
                pass

        self._thread.finished.connect(_cleanup_zombie)

        self._worker = None
        self._thread = None
        self._current_article_id = None
        self._js(
            "pipelineRunning = false;"
            "setFormLocked(false);"
            "document.getElementById('btn-stop').style.display='none';"
            "appendLog('⏹ Пайплайн остановлен. Можно запускать новую статью.', 'warn');"
        )

    def _notify(self, message: str):
        """Системное уведомление о завершении."""
        try:
            if sys.platform == "darwin":
                # display notification не поддерживает duration напрямую —
                # используем delay через повторный скрипт
                script = (
                    f'display notification "{message}" '
                    f'with title "SEO Pipeline" '
                    f'subtitle "Нажмите чтобы открыть"'
                )
                subprocess.Popen(["osascript", "-e", script])
            elif sys.platform == "linux":
                subprocess.Popen([
                    "notify-send", "-t", "5000", "SEO Pipeline", message
                ])
        except Exception:
            pass

    def _open_article_folder(self, article_id: str | None):
        aid = article_id or self._current_article_id
        if not aid:
            return
        folder = article_dir(aid)
        target = str(folder) if folder.exists() else str(ARTICLES_DIR)
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform == "win32":
            os.startfile(target)
        else:
            subprocess.Popen(["xdg-open", target])

    # ── Сигналы от пайплайна → JS ─────────────────────────────────────────────

    def _emit_cost(self):
        """Вызывается cost_tracker из потока пайплайна.
        CostBridge.cost_signal с queued connection безопасно доставит
        данные в главный поток."""
        self._cost_bridge.cost_signal.emit(
            cost_tracker.article_cost,
            cost_tracker.session_cost,
            cost_tracker.last_call_cost,
            cost_tracker.total_cost,
        )

    def _on_cost(self, article: float, session: float, last_call: float, total: float):
        self._js(
            f"updateCost({article:.5f}, {session:.5f}, "
            f"{last_call:.5f}, {total:.4f});"
        )

    def _on_review_ready(self, data: dict):
        """Показываем панель ревью в GUI."""
        self._js(f"showReviewPanel({json.dumps(data, ensure_ascii=False)});")

    def _on_resume_pipeline(self, outline_data: dict):
        """Пользователь подтвердил outline — возобновляем пайплайн."""
        if self._worker:
            self._worker.resume_with_outline(outline_data)
        self._js("hideReviewPanel();")

    def _on_log(self, msg: str):
        self._js(f"appendLog({json.dumps(msg)});")

    def _on_status(self, step: str, status: str):
        self._js(f"setStepStatus({json.dumps(step)}, {json.dumps(status)});")

    def _on_prompt(self, step: str, prompt: str, response: str):
        self._js(
            f"appendDialog({json.dumps(step)}, "
            f"{json.dumps(prompt)}, {json.dumps(response)});"
        )

    def _on_pipeline_done(self, result: dict):
        self._thread.quit()
        self._thread.wait()
        aid   = result.get("article_id")
        score = result.get("qa_score", 0)
        self._js(f"uiPipelineDone({json.dumps(score)});")
        if aid:
            self._current_article_id = aid
            data = self._bridge.getArticleResult(aid)
            self._js(f"setResult({data});")
        self._notify(f"Статья готова · QA: {score}/100")

    def _on_pipeline_error(self, error: str):
        self._thread.quit()
        self._thread.wait()
        self._js(f"appendLog({json.dumps('❌ ОШИБКА: ' + error)}, 'error');")
        self._js("uiPipelineError();")

    # ── Закрытие ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            reply = QMessageBox.question(
                self, "Выход",
                "Пайплайн ещё выполняется. Закрыть приложение?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            if self._worker:
                self._worker.stop()
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()


# ─── HTML ─────────────────────────────────────────────────────────────────────

def _build_html() -> str:
    # Подгружаем содержимое отдельных JS-модулей страниц
    _ui_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(_ui_dir, "sites_page.js"), "r", encoding="utf-8") as f:
            _sites_js = f.read()
    except Exception:
        _sites_js = "// sites_page.js не найден"
    try:
        with open(os.path.join(_ui_dir, "analytics_page.js"), "r", encoding="utf-8") as f:
            _analytics_js = f.read()
    except Exception:
        _analytics_js = "// analytics_page.js не найден"

    html = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:#1e1e2e;color:#cdd6f4;
  font-family:'SF Pro Text','Segoe UI',system-ui,sans-serif;font-size:13px;overflow:hidden}
.app{display:flex;flex-direction:column;height:100vh}

/* ══════════ LAYOUT с боковой панелью шагов ══════════ */
.app-shell{display:grid;grid-template-columns:200px 1fr;grid-template-rows:auto 1fr;
  grid-template-areas:"navsidebar topbar" "navsidebar main";height:100vh}
.nav-sidebar{grid-area:navsidebar;background:#11111b;border-right:1px solid #313244;
  display:flex;flex-direction:column;padding:18px 0;gap:4px}
.nav-sidebar-title{font-size:11px;color:#6c7086;text-transform:uppercase;
  letter-spacing:0.8px;padding:0 18px 12px 18px;font-weight:600}
.nav-step{display:flex;align-items:center;gap:10px;padding:10px 18px;
  cursor:pointer;color:#a6adc8;font-size:13px;border-left:3px solid transparent;
  transition:background .15s,color .15s}
.nav-step:hover{background:#1e1e2e;color:#cdd6f4}
.nav-step.active{background:#1e1e2e;color:#89b4fa;border-left-color:#89b4fa;
  font-weight:600}
.nav-step .ss-ico{font-size:15px}
.nav-step .ss-busy{margin-left:auto;width:6px;height:6px;border-radius:50%;
  background:#f9e2af;display:none;animation:pulse 1.5s infinite}
.nav-step.busy .ss-busy{display:inline-block}
@keyframes pulse{0%,100%{opacity:.4}50%{opacity:1}}

.topbar{grid-area:topbar}
.page-wrap{grid-area:main;overflow:auto;position:relative}
.empty-step{padding:80px 24px;text-align:center;color:#6c7086}
.empty-step h3{font-size:18px;color:#cdd6f4;margin-bottom:8px}
.empty-step p{font-size:13px;margin-bottom:18px}

/* Кнопки топбара которые видимы только на главной — управляются JS */
.tb-home-only.hidden{display:none}

/* ── TOPBAR ── */
.topbar{display:flex;align-items:center;gap:10px;padding:0 16px;height:42px;
  background:#181825;border-bottom:1px solid #313244;flex-shrink:0}
.topbar-title{font-size:14px;font-weight:600}
.topbar-sep{width:1px;height:18px;background:#313244}
.topbar-status{font-size:11px;color:#6c7086}
.topbar-right{margin-left:auto;display:flex;gap:8px;align-items:center}
.btn{border:none;border-radius:6px;padding:5px 13px;font-size:12px;font-weight:500;
  cursor:pointer;transition:background .15s;white-space:nowrap}
.btn-ghost{background:#313244;color:#a6adc8}.btn-ghost:hover{background:#45475a}
.btn-primary{background:#89b4fa;color:#1e1e2e}.btn-primary:hover{background:#b4befe}
.btn-danger{background:#f38ba8;color:#1e1e2e}.btn-danger:hover{background:#eba0ac}
.btn-sm{padding:3px 10px;font-size:11px}
.btn:disabled{opacity:.4;cursor:default;pointer-events:none}

/* ── COST BAR ── */
.cost-bar{display:flex;align-items:center;gap:0}
.cost-item{display:flex;flex-direction:column;align-items:center;padding:0 10px}
.cost-label{font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#45475a;line-height:1}
.cost-val{font-size:12px;font-weight:600;color:#6c7086;font-family:monospace;line-height:1.4}
.cost-val-total{color:#89b4fa}
.cost-sep{width:1px;height:24px;background:#313244}

/* ── PAGES ── */
.page{display:none;flex:1;overflow:hidden;flex-direction:column}
.page.active{display:flex}

/* ══ PAGE: FORM ══ */
.form-page{overflow-y:auto;padding:20px 24px 28px}
.form-page-inner{max-width:800px;margin:0 auto}
.form-h{font-size:16px;font-weight:600;margin-bottom:3px}
.form-sub{font-size:12px;color:#6c7086;margin-bottom:18px}
.section{margin-bottom:16px}
.section-label{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:#6c7086;margin-bottom:8px}
.grid{display:grid;gap:9px}
.g2{grid-template-columns:1fr 1fr}
.g3{grid-template-columns:1fr 1fr 1fr}
.span2{grid-column:span 2}.span3{grid-column:span 3}
.field{display:flex;flex-direction:column;gap:3px}
.field label{font-size:11px;color:#6c7086;display:flex;align-items:center;gap:5px}
.field input,.field select,.field textarea{
  background:#313244;border:1px solid #45475a;border-radius:6px;
  padding:6px 10px;color:#cdd6f4;font-size:12px;font-family:inherit;
  outline:none;transition:border-color .15s;width:100%}
.field input:focus,.field select:focus,.field textarea:focus{border-color:#89b4fa}
.field select option{background:#313244}
.field textarea{resize:vertical}
.field input:disabled,.field select:disabled,.field textarea:disabled{opacity:.5;cursor:not-allowed}
.tip{display:inline-flex;align-items:center;justify-content:center;
  width:15px;height:15px;background:#45475a;border-radius:50%;
  color:#89b4fa;font-size:9px;font-weight:700;cursor:help;flex-shrink:0}
.serp-zone{background:#181825;border:1.5px dashed #45475a;border-radius:8px;
  padding:16px;cursor:pointer;transition:border-color .2s, background .2s;text-align:center}
.serp-zone:hover{border-color:#89b4fa}
.serp-zone.drag-over{border-color:#89b4fa;background:#1a2a3a;border-style:solid}
.serp-zone.loaded{border-style:solid;border-color:#a6e3a1;text-align:left;cursor:default}
.serp-row{display:flex;align-items:center;gap:10px}
.serp-ok{font-size:16px;color:#a6e3a1}
.serp-name{font-size:12px;color:#a6e3a1;font-weight:500}
.serp-meta{font-size:11px;color:#6c7086}
.btn-xs{background:#313244;color:#a6adc8;border:none;border-radius:5px;
  padding:3px 9px;font-size:11px;cursor:pointer}
.btn-xs:hover{background:#45475a}
.pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
.pill{display:inline-flex;align-items:center;gap:5px;background:#313244;border-radius:6px;
  padding:4px 10px;font-size:12px;color:#a6adc8;cursor:pointer;user-select:none}
.pill:hover{background:#45475a}
.pill input{accent-color:#89b4fa;width:13px;height:13px;cursor:pointer}
.strategy-pills{display:flex;flex-wrap:wrap;gap:6px}
.strategy-pills .pill:has(input:checked){background:#45475a;color:#cdd6f4;
  border:1px solid #89b4fa}
.strat-mult{color:#6c7086;font-size:10px;margin-left:4px}
.chk-row{display:flex;align-items:center;gap:7px;font-size:12px;color:#a6adc8;
  cursor:pointer;margin-top:8px}
.chk-row input{accent-color:#89b4fa;width:13px;height:13px}
.form-footer{display:flex;gap:8px;margin-top:20px;padding-top:14px;
  border-top:1px solid #313244;align-items:center}

/* ══ PAGE: MONITOR ══ */
.monitor-page{flex-direction:row}
.sidebar{width:250px;background:#181825;border-right:1px solid #313244;
  display:flex;flex-direction:column;flex-shrink:0}

/* Зона 1 — Hero */
.sb-hero{padding:12px 14px;border-bottom:1px solid #313244;flex-shrink:0}
.sb-hero-agent{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:#6c7086;margin-bottom:4px;display:flex;align-items:center;gap:5px}
.sb-hero-dot{width:6px;height:6px;border-radius:50%;background:#6c7086;flex-shrink:0}
.sb-hero-dot.running{background:#89b4fa;animation:pulse 1s infinite}
.sb-hero-dot.done{background:#a6e3a1}
.sb-hero-dot.error{background:#f38ba8}
.sb-hero-dot.weak{background:#fab387}
.sb-hero-action{font-size:13px;font-weight:600;color:#cdd6f4;line-height:1.3;
  margin-bottom:2px;word-break:break-word}
.sb-hero-detail{font-size:11px;color:#6c7086;line-height:1.4}

/* Зона 2 — Плоский список этапов */
.sb-steps{flex:0 0 auto;overflow-y:auto;max-height:60%;padding:6px 0}
.step-item{display:flex;flex-direction:column}
.step-hdr{display:flex;align-items:center;gap:8px;padding:4px 14px}
.step-ic{width:15px;height:15px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;
  background:#313244;color:#6c7086}
.step-ic.done{background:#1a3a2a;color:#a6e3a1}
.step-ic.running{background:#1a2a3a;color:#89b4fa;animation:pulse 1s infinite}
.step-ic.error{background:#3a1a1a;color:#f38ba8}
.step-ic.weak{background:#3a2a1a;color:#fab387}
.step-tx{font-size:12px;color:#45475a;line-height:1.3}
.step-tx.done{color:#a6e3a1}
.step-tx.running{color:#89b4fa;font-weight:600}
.step-tx.error{color:#f38ba8}
/* Детали под активным шагом — прямо в потоке */
.step-events{padding:2px 14px 5px 37px}
.step-event{font-size:11px;color:#6c7086;line-height:1.6;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.step-event.fresh{color:#a6adc8}

/* Зона 3 — Секции */
.sb-sections{flex:1;overflow-y:auto;border-top:1px solid #313244;min-height:0}
.sb-sections-hdr{display:flex;align-items:center;justify-content:space-between;
  padding:7px 14px 4px;position:sticky;top:0;background:#181825;z-index:1}
.sb-sec-label{font-size:9px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:#45475a}
.sb-sec-count{font-size:10px;color:#6c7086;font-family:monospace}
.sec-progress{margin:0 14px 6px;height:3px;background:#313244;border-radius:2px}
.sec-progress-bar{height:100%;background:#89b4fa;border-radius:2px;
  transition:width .4s ease;width:0%}
.sec-row{display:flex;align-items:center;gap:7px;padding:3px 14px;
  transition:background .1s}
.sec-row.active{background:#1a2a3a}
.sec-ic{font-size:11px;width:14px;flex-shrink:0;text-align:center}
.sec-name{font-size:11px;color:#45475a;line-height:1.3;flex:1;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sec-name.done{color:#a6e3a1}
.sec-name.running{color:#89b4fa;font-weight:500}
.sec-name.weak{color:#fab387}
.sec-name.error{color:#f38ba8}
.sec-iter{font-size:10px;color:#45475a;flex-shrink:0;font-family:monospace}

.sb-bottom{padding:8px 10px;border-top:1px solid #313244;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.mon-content{flex:1;display:flex;flex-direction:column;overflow:hidden}
.tab-bar{display:flex;background:#181825;border-bottom:1px solid #313244;flex-shrink:0;align-items:center}
.tab{padding:8px 15px;font-size:12px;font-weight:500;color:#6c7086;cursor:pointer;
  border-bottom:2px solid transparent;transition:all .15s;user-select:none}
.tab:hover{color:#cdd6f4}.tab.active{color:#89b4fa;border-bottom-color:#89b4fa;background:#1e1e2e}
.tab-cnt{display:inline-block;background:#313244;color:#89b4fa;border-radius:10px;
  padding:1px 6px;font-size:10px;margin-left:4px}
.tab.active .tab-cnt{background:#1a2a3a}
.pv-switcher{margin-left:auto;display:none;align-items:center;padding:0 12px;gap:0}
.pv-btn{background:#313244;color:#a6adc8;border:none;padding:4px 11px;font-size:11px;
  font-weight:500;cursor:pointer}
.pv-btn:first-child{border-radius:6px 0 0 6px}
.pv-btn:last-child{border-radius:0 6px 6px 0}
.pv-btn.active{background:#89b4fa;color:#1e1e2e;font-weight:600}
.tab-panel{display:none;flex:1;overflow-y:auto;padding:10px 13px}
.tab-panel.active{display:block}

/* Log */
.log-line{display:flex;gap:9px;padding:2px 0;border-bottom:1px solid #181825}
.log-t{color:#45475a;font-size:11px;font-family:monospace;flex-shrink:0;padding-top:1px}
.log-m{font-size:12px;color:#a6adc8;line-height:1.5}
.log-m.info{color:#89b4fa}.log-m.ok{color:#a6e3a1}.log-m.warn{color:#f9e2af}.log-m.error{color:#f38ba8}

/* Dialog */
.dialog-area{display:flex;flex-direction:column;gap:7px;padding-bottom:8px}
.msg-row{display:flex;flex-direction:column;max-width:80%}
.msg-row.left{align-self:flex-start;align-items:flex-start}
.msg-row.right{align-self:flex-end;align-items:flex-end}
.msg-lbl{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:2px;padding:0 3px}
.bubble{border-radius:14px;padding:8px 12px;font-size:12px;line-height:1.6;
  max-width:100%;word-break:break-word}
.msg-row.left .bubble{background:#313244;color:#cdd6f4;border-bottom-left-radius:3px}
.msg-row.right .bubble{background:#1a3a5c;color:#cdd6f4;border-bottom-right-radius:3px}
.msg-row.left.critic .bubble{border-left:3px solid #f38ba8;border-bottom-left-radius:0}
.msg-row.left.editor .bubble{border-left:3px solid #fab387;border-bottom-left-radius:0}
.msg-row.left.analyst .bubble{border-left:3px solid #89b4fa;border-bottom-left-radius:0}
.msg-row.left.qa .bubble{border-left:3px solid #cba6f7;border-bottom-left-radius:0}
.msg-row.left.meta .bubble{border-left:3px solid #94e2d5;border-bottom-left-radius:0}
.role-writer{color:#a6e3a1}.role-critic{color:#f38ba8}.role-editor{color:#fab387}
.role-analyst{color:#89b4fa}.role-qa{color:#cba6f7}.role-meta{color:#94e2d5}
.bub-meta{display:flex;gap:7px;margin-top:3px;padding:0 2px}
.bub-model,.bub-time{font-size:10px;color:#45475a}
.prompt-tog{font-size:10px;color:#6c7086;cursor:pointer;margin-bottom:5px;
  display:inline-flex;align-items:center;gap:3px;padding:2px 6px;
  background:rgba(0,0,0,.15);border-radius:4px;user-select:none}
.prompt-tog:hover{color:#89b4fa}
.prompt-body{background:rgba(0,0,0,.2);border-radius:5px;padding:5px 8px;font-size:11px;
  color:#6c7086;line-height:1.5;margin-bottom:7px;display:none;white-space:pre-wrap}
.prompt-body.open{display:block}
.resp-body{font-size:12px;line-height:1.65;color:#cdd6f4}
.resp-body b{color:#f5c2e7;font-weight:600}.resp-body i{color:#cba6f7}
.resp-body code{background:rgba(0,0,0,.3);padding:1px 4px;border-radius:3px;
  font-family:monospace;font-size:11px}
.sys-msg{align-self:center;background:#313244;color:#6c7086;font-size:11px;
  border-radius:10px;padding:3px 10px;margin:3px 0}

/* Result */
.res-hdr{display:flex;align-items:center;gap:12px;margin-bottom:14px;
  padding:12px 14px;background:#181825;border-radius:8px}
.qa-circle{width:56px;height:56px;border-radius:50%;display:flex;flex-direction:column;
  align-items:center;justify-content:center;border:3px solid #a6e3a1;flex-shrink:0}
.qa-num{font-size:19px;font-weight:700;color:#a6e3a1;line-height:1}
.qa-lbl{font-size:9px;color:#6c7086;text-transform:uppercase}
.res-status{font-size:14px;font-weight:600;color:#a6e3a1}
.res-rec{font-size:12px;color:#a6adc8;margin-top:2px;line-height:1.5}
.res-fields{background:#181825;border-radius:8px;padding:9px 12px;margin-bottom:11px}
.f-row{display:flex;gap:8px;padding:3px 0;border-bottom:1px solid #313244}
.f-row:last-child{border:none}
.f-key{color:#6c7086;font-size:11px;width:125px;flex-shrink:0;padding-top:1px}
.f-val{color:#cdd6f4;font-size:12px;flex:1;line-height:1.4}
.warn-box{background:#2a2010;border-left:3px solid #f9e2af;border-radius:0;
  padding:9px 13px;margin-bottom:11px}
.warn-item{color:#f9e2af;font-size:12px;line-height:1.7}

/* QA criteria визуализация */
.qa-criteria-card{background:#181825;border-radius:8px;padding:14px;margin-bottom:12px}
.qa-criteria-title{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:#6c7086;margin-bottom:12px}
.qa-crit-row{display:flex;align-items:center;gap:8px;margin-bottom:7px}
.qa-crit-label{font-size:11px;color:#a6adc8;width:120px;flex-shrink:0}
.qa-crit-bar-wrap{flex:1;height:6px;background:#313244;border-radius:3px;overflow:hidden}
.qa-crit-bar{height:100%;border-radius:3px;transition:width .4s ease}
.qa-crit-val{font-size:11px;font-weight:600;width:28px;text-align:right;flex-shrink:0}
.qa-crit-type{font-size:9px;width:30px;text-align:right;flex-shrink:0;opacity:.5}
.qa-crit-row.code .qa-crit-bar{background:#1D9E75}
.qa-crit-row.llm  .qa-crit-bar{background:#f38ba8}
.qa-legend{display:flex;gap:14px;margin-top:10px;padding-top:8px;
  border-top:1px solid #313244}
.qa-leg-item{display:flex;align-items:center;gap:5px;font-size:10px;color:#6c7086}
.qa-leg-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}

/* Точки роста — чекбоксы */
.gap-item{background:#181825;border:1px solid #313244;border-radius:6px;
  padding:8px 10px;margin-bottom:6px;cursor:pointer;transition:border-color .15s}
.gap-item:hover{border-color:#45475a}
.gap-item.selected{border-color:#a6e3a1;background:#0d1f14}
.gap-item-row{display:flex;align-items:flex-start;gap:8px}
.gap-cb{width:14px;height:14px;accent-color:#a6e3a1;cursor:pointer;flex-shrink:0;margin-top:2px}
.gap-content{flex:1}
.gap-title{font-size:12px;color:#cdd6f4;font-weight:500;margin-bottom:2px}
.gap-desc{font-size:11px;color:#6c7086;line-height:1.4;margin-bottom:3px}
.gap-meta{display:flex;gap:8px;flex-wrap:wrap}
.gap-after{font-size:10px;color:#89b4fa}
.gap-words{font-size:10px;color:#45475a}
.pv-body{background:#181825;border-radius:8px;padding:13px 15px}
.pv-raw{font-size:12px;line-height:1.75;color:#cdd6f4;white-space:pre-wrap;
  font-family:monospace}
.pv-rendered{font-size:13px;line-height:1.8;color:#cdd6f4}
.pv-rendered img{max-width:100%;height:auto;display:block;margin:10px 0;border-radius:6px}
.pv-rendered h1{font-size:19px;font-weight:600;color:#89b4fa;margin:14px 0 7px}
.pv-rendered h2{font-size:15px;font-weight:600;color:#89b4fa;margin:12px 0 5px}
.pv-rendered h3{font-size:13px;font-weight:600;color:#cba6f7;margin:9px 0 3px}
.pv-rendered p{margin-bottom:9px}.pv-rendered strong{color:#f5c2e7;font-weight:600}
.pv-rendered em{color:#cba6f7}
.pv-rendered ul,.pv-rendered ol{padding-left:18px;margin-bottom:9px}
.pv-rendered li{margin-bottom:3px;line-height:1.6}
.pv-rendered code{background:#313244;padding:1px 4px;border-radius:4px;
  font-size:11px;font-family:monospace}
.pv-rendered pre{background:#313244;padding:10px 12px;border-radius:6px;
  margin-bottom:10px;overflow-x:auto}
.pv-rendered pre code{background:none;padding:0;font-size:12px}
.pv-rendered blockquote{border-left:3px solid #45475a;padding:4px 12px;
  margin:8px 0;color:#6c7086}
.pv-rendered hr{border:none;border-top:1px solid #313244;margin:12px 0}
.pv-rendered table{border-collapse:collapse;width:100%;margin-bottom:12px;font-size:12px}
.pv-rendered th{background:#313244;color:#cdd6f4;font-weight:600;
  padding:7px 10px;border:1px solid #45475a;text-align:left}
.pv-rendered td{padding:6px 10px;border:1px solid #313244;color:#a6adc8;
  vertical-align:top}
.pv-rendered tr:nth-child(even) td{background:#1a1a2a}

/* ══ REVIEW PANEL (overlay поверх монитора) ══ */
.review-overlay{display:none;position:absolute;inset:0;background:rgba(0,0,0,.6);
  z-index:100;align-items:center;justify-content:center}
.review-overlay.active{display:flex}
.review-panel{background:#1e1e2e;border:1px solid #45475a;border-radius:12px;
  width:880px;max-height:85vh;display:flex;flex-direction:column;overflow:hidden}
.review-panel-hdr{padding:16px 20px;border-bottom:1px solid #313244;
  display:flex;align-items:center;gap:12px;flex-shrink:0}
.review-panel-title{font-size:15px;font-weight:600;color:#cdd6f4;flex:1}
.review-panel-body{display:flex;gap:0;flex:1;overflow:hidden}
.review-left{width:300px;border-right:1px solid #313244;overflow-y:auto;
  padding:16px;flex-shrink:0}
.review-right{flex:1;overflow-y:auto;padding:16px}
.review-section-title{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:#6c7086;margin-bottom:10px}

/* Competitor stats */
.stat-block{background:#181825;border-radius:8px;padding:12px;margin-bottom:10px}
.stat-label{font-size:11px;color:#6c7086;margin-bottom:4px}
.stat-values{font-size:12px;color:#a6adc8;margin-bottom:4px}
.stat-rec{font-size:12px;font-weight:600;color:#89b4fa}
.h2-title-row{display:flex;align-items:center;gap:8px;padding:3px 0;
  border-bottom:1px solid #1e1e2e}
.h2-title-name{font-size:12px;color:#a6adc8;flex:1}
.h2-title-freq{font-size:11px;color:#6c7086;font-family:monospace;flex-shrink:0}
.h2-title-bar{height:4px;background:#89b4fa;border-radius:2px;margin-top:2px}

/* Outline editor */
.outline-h1{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.outline-h1 input{flex:1;background:#313244;border:1px solid #45475a;border-radius:6px;
  padding:6px 10px;color:#cdd6f4;font-size:13px;font-weight:600;outline:none}
.outline-h1 input:focus{border-color:#89b4fa}
.sec-editor-list{display:flex;flex-direction:column;gap:6px}
.sec-editor-item{background:#181825;border:1px solid #313244;border-radius:8px;
  padding:10px 12px;cursor:grab;transition:border-color .15s}
.sec-editor-item:hover{border-color:#45475a}
.sec-editor-item.dragging{opacity:.4;border-color:#89b4fa}
.sec-editor-item.drag-over-top{border-top:2px solid #89b4fa}
.sec-editor-item.drag-over-bot{border-bottom:2px solid #89b4fa}
.sec-editor-row{display:flex;align-items:center;gap:8px}
.sec-drag-handle{color:#45475a;font-size:14px;cursor:grab;flex-shrink:0;user-select:none}
.sec-editor-title{flex:1;background:transparent;border:none;border-bottom:1px solid #45475a;
  color:#cdd6f4;font-size:12px;padding:2px 4px;outline:none;min-width:0}
.sec-editor-title:focus{border-bottom-color:#89b4fa}
.sec-editor-words{width:70px;background:#313244;border:1px solid #45475a;border-radius:4px;
  color:#a6adc8;font-size:11px;padding:2px 6px;outline:none;text-align:center}
.sec-editor-words:focus{border-color:#89b4fa}
.sec-del-btn{background:none;border:none;color:#45475a;font-size:16px;cursor:pointer;
  flex-shrink:0;padding:0 2px;line-height:1}
.sec-del-btn:hover{color:#f38ba8}
.sec-add-btn{background:#313244;border:1px dashed #45475a;border-radius:8px;
  color:#6c7086;font-size:12px;padding:8px;cursor:pointer;text-align:center;
  transition:all .15s;margin-top:4px}
.sec-add-btn:hover{border-color:#89b4fa;color:#89b4fa}
.sec-total{font-size:11px;color:#6c7086;text-align:right;margin-top:8px}

.review-footer{padding:14px 20px;border-top:1px solid #313244;
  display:flex;gap:10px;justify-content:flex-end;flex-shrink:0}
.review-panel .mon-content{position:relative}
.history-page{overflow:hidden;flex-direction:row}
.hist-list{width:270px;border-right:1px solid #313244;display:flex;flex-direction:column;flex-shrink:0}
.hist-list-top{padding:10px 13px;border-bottom:1px solid #313244;display:flex;align-items:center;gap:8px}
.hist-list-title{font-size:13px;font-weight:600;flex:1}
.hist-items{flex:1;overflow-y:auto}
.hist-item{padding:9px 13px;border-bottom:1px solid #181825;cursor:pointer;transition:background .1s}
.hist-item:hover{background:#181825}.hist-item.active{background:#1a2a3a}
.hist-item-title{font-size:12px;color:#cdd6f4;font-weight:500;margin-bottom:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hist-item-meta{display:flex;gap:7px;align-items:center}
.hist-item-date{font-size:11px;color:#6c7086}
.hbadge{font-size:10px;border-radius:10px;padding:1px 7px}
.hbadge-pass{background:#1a3a2a;color:#a6e3a1}
.hbadge-fail{background:#3a1a1a;color:#f38ba8}
.hbadge-warn{background:#3a2a1a;color:#fab387}
.hist-detail{flex:1;overflow-y:auto;padding:18px 22px}
.hist-empty{display:flex;align-items:center;justify-content:center;flex:1;
  color:#45475a;font-size:13px}
.empty-state{padding:36px 0;text-align:center;color:#45475a;font-size:12px}
</style>
</head>
<body>
<div class="app">

<!-- TOPBAR -->
<div class="app-shell">

<aside class="nav-sidebar">
  <div class="nav-sidebar-title">Этапы</div>
  <div class="nav-step active" id="ss-home" onclick="goToStep('home')">
    <span class="ss-ico">🏠</span><span>Главная</span><span class="ss-busy"></span>
  </div>
  <div class="nav-step" id="ss-writing" onclick="goToStep('writing')">
    <span class="ss-ico">✍️</span><span>Написание</span><span class="ss-busy"></span>
  </div>
  <div class="nav-step" id="ss-result" onclick="goToStep('result')">
    <span class="ss-ico">✅</span><span>Результат</span><span class="ss-busy"></span>
  </div>
</aside>

<div class="topbar">
  <span class="topbar-title">SEO Pipeline</span>
  <div class="topbar-sep"></div>
  <span class="topbar-status" id="topbar-status">Готов к работе</span>
  <div class="topbar-sep"></div>
  <div class="cost-bar" id="cost-bar">
    <div class="cost-item">
      <span class="cost-label">статья</span>
      <span class="cost-val" id="c-article">$0.0000</span>
    </div>
    <div class="cost-sep"></div>
    <div class="cost-item">
      <span class="cost-label">сессия</span>
      <span class="cost-val" id="c-session">$0.0000</span>
    </div>
    <div class="cost-sep"></div>
    <div class="cost-item">
      <span class="cost-label">последний запрос</span>
      <span class="cost-val" id="c-last">$0.00000</span>
    </div>
    <div class="cost-sep"></div>
    <div class="cost-item">
      <span class="cost-label">всего</span>
      <span class="cost-val cost-val-total" id="c-total">$0.0000</span>
    </div>
  </div>
  <div class="topbar-right">
    <button class="btn btn-ghost btn-sm tb-home-only" onclick="showPage('sites')">Сайты</button>
    <button class="btn btn-ghost btn-sm tb-home-only" onclick="showPage('analytics')">Аналитика</button>
    <button class="btn btn-ghost btn-sm tb-home-only" onclick="showPage('history')">История статей</button>
    <button class="btn btn-danger btn-sm" id="btn-stop" style="display:none" onclick="bridge&&bridge.stopPipeline()">Остановить</button>
    <button class="btn btn-ghost btn-sm" id="btn-copy" style="display:none" onclick="copyArticle()" title="Копировать markdown в буфер">Копировать статью</button>
    <button class="btn btn-ghost btn-sm" id="btn-folder" style="display:none" onclick="bridge&&bridge.openCurrentFolder()">Открыть папку</button>
  </div>
</div>

<div class="page-wrap">

<!-- ══════════ PAGE: FORM ══════════ -->
<div class="page active form-page" id="page-form">
<div class="form-page-inner">
  <div class="form-h">Новая статья</div>
  <div class="form-sub">Заполните параметры генерации и загрузите SERP-данные</div>

  <div class="section">
    <div class="section-label">Сайт</div>
    <div class="grid g2">
      <div class="field span2">
        <label>Для какого сайта статья? *</label>
        <select id="f-site"><option value="">— загрузка сайтов… —</option></select>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-label">Основные параметры</div>
    <div class="grid g2">
      <div class="field span2">
        <label>Название статьи *</label>
        <input type="text" id="f-title" placeholder="Погода в Турции в мае">
      </div>
      <div class="field">
        <label>Главный ключ *</label>
        <input type="text" id="f-mainkey" placeholder="погода в турции в мае">
      </div>
      <div class="field">
        <label>Гео *</label>
        <input type="text" id="f-geo" placeholder="Россия">
      </div>
      <div class="field span2">
        <label>Второстепенные ключи * <span style="color:#6c7086;font-weight:400">(один на строку)</span></label>
        <textarea id="f-seckeys" rows="3" placeholder="один ключ на строку"></textarea>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-label">Параметры</div>
    <div class="grid g3">
      <div class="field" style="grid-column:span 3">
        <label>Стратегия объёма *</label>
        <div class="strategy-pills">
          <label class="pill">
            <input type="radio" name="length-strategy" value="shorter_top" onchange="onStrategyChange()">
            <span>Короче топа <span class="strat-mult">0.7 × avg</span></span>
          </label>
          <label class="pill">
            <input type="radio" name="length-strategy" value="match_top" checked onchange="onStrategyChange()">
            <span>Как топ <span class="strat-mult">1.0 × avg</span></span>
          </label>
          <label class="pill">
            <input type="radio" name="length-strategy" value="longer_top" onchange="onStrategyChange()">
            <span>Длиннее топа <span class="strat-mult">1.3 × avg</span></span>
          </label>
          <label class="pill">
            <input type="radio" name="length-strategy" value="custom" onchange="onStrategyChange()">
            <span>Пользовательская длина</span>
          </label>
        </div>
        <div id="f-words-wrap" style="display:none;margin-top:8px">
          <input type="number" id="f-words" value="1200" min="300" max="10000" step="100"
                 placeholder="Кол-во слов" style="max-width:200px">
        </div>
      </div>
      <div class="field">
        <label>Язык *</label>
        <select id="f-lang">
          <option value="ru">ru</option>
          <option value="en">en</option>
          <option value="sv">sv</option>
          <option value="de">de</option>
          <option value="fr">fr</option>
        </select>
      </div>
      <div class="field">
        <label>Интент</label>
        <select id="f-intent">
          <option value="">— определить автоматически —</option>
          <option value="informational">informational</option>
          <option value="how_to">how_to</option>
        </select>
      </div>
      <div class="field">
        <label>Тип статьи *</label>
        <select id="f-type">
          <option value="informational">informational</option>
          <option value="how_to">how_to</option>
        </select>
      </div>
      <div class="field">
        <label>Сложность *
          <span class="tip" title="easy — простая тема, широкая аудитория&#10;medium — требует базовых знаний&#10;hard — экспертная, терминология ок">?</span>
        </label>
        <select id="f-difficulty">
          <option value="easy">easy</option>
          <option value="medium" selected>medium</option>
          <option value="hard">hard</option>
        </select>
      </div>
      <div class="field">
        <label>Стиль *</label>
        <select id="f-style">
          <option value="expert_clear">expert_clear</option>
          <option value="friendly_practical">friendly_practical</option>
          <option value="calm_analytical">calm_analytical</option>
          <option value="editorial_neutral">editorial_neutral</option>
        </select>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-label">SERP данные (JSON от краулера)</div>
    <div class="serp-zone" id="serp-zone" onclick="handleSerpClick()">
      <div id="serp-empty" style="text-align:center">
        <div style="font-size:20px;color:#45475a;margin-bottom:5px">↑</div>
        <div style="font-size:13px;color:#a6adc8;margin-bottom:8px">Загрузить JSON от краулера</div>
        <div style="font-size:11px;color:#6c7086">Нажмите в любом месте или перетащите файл</div>
      </div>
      <div id="serp-loaded" style="display:none">
        <div class="serp-row">
          <div class="serp-ok">✓</div>
          <div style="flex:1">
            <div class="serp-name" id="serp-fname"></div>
            <div class="serp-meta" id="serp-meta"></div>
          </div>
          <button class="btn-xs" onclick="event.stopPropagation();clearSerp()">Удалить</button>
        </div>
      </div>
    </div>
    <label class="chk-row">
      <input type="checkbox" id="f-refresh-serp"> Обновить кеш (загрузить файл заново)
    </label>
  </div>

  <div class="section">
    <div class="section-label">Ограничения и обязательные элементы</div>
    <div class="grid g2">
      <div class="field">
        <label>Запрещённые слова <span style="color:#6c7086;font-weight:400">(один на строку)</span></label>
        <textarea id="f-forbidden" rows="3" placeholder="в заключение&#10;как известно"></textarea>
      </div>
      <div class="field">
        <label>Дополнительные заметки</label>
        <textarea id="f-notes" rows="3" placeholder="Дополнительные указания..."></textarea>
      </div>
    </div>
    <div style="margin-top:9px">
      <div style="font-size:11px;color:#6c7086;margin-bottom:6px">Обязательные элементы</div>
      <div class="pills">
        <label class="pill"><input type="checkbox" id="chk-faq" checked> faq</label>
        <label class="pill"><input type="checkbox" id="chk-quick" checked> quick_answer</label>
        <label class="pill"><input type="checkbox" id="chk-table"> table</label>
        <label class="pill"><input type="checkbox" id="chk-list"> list</label>
        <label class="pill"><input type="checkbox" id="chk-concl" checked> conclusion</label>
        <label class="pill"><input type="checkbox" id="chk-sources"> sources_block</label>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-label">Настройки пайплайна</div>
    <label class="chk-row">
      <input type="checkbox" id="chk-always-review" checked>
      Проверять каждую секцию через Critic
      <span class="tip" title="ВКЛ: каждую секцию проверяет Claude Critic — качественнее, дороже&#10;ВЫКЛ: Writer делает self-check, Critic только при проблемах">?</span>
    </label>
  </div>

  <div class="form-footer">
    <button class="btn btn-primary" id="btn-run" onclick="onRunClicked()">▶ Запустить пайплайн</button>
    <button class="btn btn-ghost" id="btn-validate" onclick="onValidateClicked()">Проверить данные</button>
    <button class="btn btn-ghost" onclick="fillDemo()">Заполнить по примеру</button>
    <button class="btn btn-ghost" style="margin-left:auto" onclick="clearForm()">Очистить форму</button>
  </div>
</div>
</div>

<!-- ══════════ PAGE: MONITOR ══════════ -->
<div class="page monitor-page" id="page-monitor">
  <div class="sidebar">

    <!-- Зона 1: Hero — текущий статус крупно -->
    <div class="sb-hero">
      <div class="sb-hero-agent">
        <div class="sb-hero-dot" id="hero-dot"></div>
        <span id="hero-agent">Ожидание</span>
      </div>
      <div class="sb-hero-action" id="hero-action">—</div>
      <div class="sb-hero-detail" id="hero-detail"></div>
    </div>

    <!-- Зона 2: Этапы-аккордеон -->
    <div class="sb-steps" id="steps-container"></div>

    <!-- Зона 3: Секции (появляется после outline) -->
    <div class="sb-sections" id="sb-sections" style="display:none">
      <div class="sb-sections-hdr">
        <span class="sb-sec-label">Секции</span>
        <span class="sb-sec-count" id="sec-count">0/0</span>
      </div>
      <div class="sec-progress"><div class="sec-progress-bar" id="sec-pbar"></div></div>
      <div id="sec-list"></div>
    </div>

    <div class="sb-bottom">
    </div>
  </div>
  <div class="mon-content" style="position:relative">

    <!-- Review overlay -->
    <div class="review-overlay" id="review-overlay">
      <div class="review-panel">
        <div class="review-panel-hdr">
          <div class="review-panel-title">Проверьте структуру статьи перед генерацией</div>
          <span style="font-size:11px;color:#6c7086">Пайплайн на паузе ⏸</span>
        </div>
        <div class="review-panel-body">
          <!-- Левая колонка: данные конкурентов -->
          <div class="review-left">
            <div class="review-section-title">Анализ конкурентов</div>
            <div id="review-competitor-stats"></div>
            <div class="review-section-title" style="margin-top:14px">Частые H2 блоки</div>
            <div id="review-h2-titles"></div>
            <div class="review-section-title" style="margin-top:14px">Must-have темы</div>
            <div id="review-must-have"></div>
            <div class="review-section-title" style="margin-top:14px">Точки роста</div>
            <div style="font-size:10px;color:#6c7086;margin-bottom:6px">Отметь — добавятся в структуру</div>
            <div id="review-gaps"></div>
          </div>
          <!-- Правая колонка: редактор outline -->
          <div class="review-right">
            <div class="review-section-title">Архетип статьи</div>
            <div id="review-archetype" style="background:#181825;border:1px solid #313244;border-radius:6px;padding:10px;margin-bottom:14px"></div>
            <div class="review-section-title">Структура статьи (редактируй)</div>
            <div class="outline-h1">
              <span style="font-size:11px;color:#6c7086;flex-shrink:0">H1</span>
              <input type="text" id="outline-h1" placeholder="Заголовок статьи">
            </div>
            <div class="sec-editor-list" id="sec-editor-list"></div>
            <div class="sec-add-btn" onclick="addSection()">+ Добавить секцию</div>
            <div class="sec-total" id="sec-total"></div>
          </div>
        </div>
        <div class="review-footer">
          <button class="btn btn-ghost" onclick="cancelReview()">Отменить генерацию</button>
          <button class="btn btn-primary" onclick="confirmReview()">Продолжить генерацию →</button>
        </div>
      </div>
    </div>
    <div class="tab-bar">
      <div class="tab active" data-tab="log" onclick="switchTab('log')">Лог <span class="tab-cnt" id="cnt-log">0</span></div>
      <div class="tab" data-tab="dialog" onclick="switchTab('dialog')">Диалог агентов <span class="tab-cnt" id="cnt-dlg">0</span></div>
      <div class="tab" data-tab="result" onclick="switchTab('result')">Результат</div>
      <div id="pv-switcher" style="display:none;align-items:center;padding:0 12px;margin-left:auto">
        <button class="pv-btn" id="btn-preview-toggle" onclick="togglePreview()">Предпросмотр</button>
      </div>
    </div>
    <div class="tab-panel active" id="panel-log"><div id="log-list"></div></div>
    <div class="tab-panel" id="panel-dialog"><div class="dialog-area" id="dialog-list"></div></div>
    <div class="tab-panel" id="panel-result">
      <div id="result-content"><div class="empty-state">Результат появится после завершения пайплайна</div></div>
    </div>
  </div>
</div>

<!-- ══════════ PAGE: RESULT (заглушка/контейнер) ══════════ -->
<div class="page" id="page-result" style="padding:24px;overflow:auto">
  <div id="result-empty" class="empty-step">
    <h3>Результата пока нет</h3>
    <p>Сначала создайте статью на главной — после завершения вы попадёте сюда автоматически.</p>
  </div>
  <div id="result-busy" class="empty-step" style="display:none">
    <h3>Генерация в процессе</h3>
    <p>Пайплайн ещё работает — результат появится здесь автоматически по завершении.</p>
  </div>
</div>

<!-- ══════════ PAGE: HISTORY ══════════ -->
<div class="page history-page" id="page-history">
  <div class="hist-list">
    <div class="hist-list-top">
      <span class="hist-list-title">История статей</span>
      <button class="btn btn-ghost btn-sm" onclick="showPage('form')">← Назад</button>
      <button class="btn btn-ghost btn-sm" onclick="loadHistory()">↻</button>
    </div>
    <div class="hist-items" id="hist-items"></div>
  </div>
  <div style="flex:1;display:flex;overflow:hidden">
    <div class="hist-empty" id="hist-empty">Выберите статью из списка</div>
    <div class="hist-detail" id="hist-detail" style="display:none"></div>
  </div>
</div>

<!-- ══════════ PAGE: SITES ══════════ -->
<!-- ══════════ PAGE: ANALYTICS ══════════ -->
<div class="page" id="page-analytics" style="padding:24px;overflow:auto">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <h2 style="margin:0">Аналитика</h2>
    <div>
      <button class="btn btn-ghost btn-sm" onclick="showPage('form')">← Назад</button>
      <button class="btn btn-ghost btn-sm" onclick="loadAnalyticsPage()">↻</button>
      <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#6c7086;cursor:pointer;margin-left:12px;vertical-align:middle">
        <input type="checkbox" id="an-show-test" onchange="loadAnalyticsPage()" style="width:auto;margin:0">
        показать тестовые сайты
      </label>
    </div>
  </div>

  <div id="an-summary" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px"></div>

  <div style="margin-bottom:24px">
    <h3 style="margin:0 0 8px 0;font-size:15px">По сайтам</h3>
    <div id="an-sites"></div>
  </div>

  <div style="margin-bottom:24px">
    <h3 style="margin:0 0 8px 0;font-size:15px">По нишам</h3>
    <div id="an-niches"></div>
  </div>

  <div style="margin-bottom:24px">
    <h3 style="margin:0 0 8px 0;font-size:15px">По архетипам</h3>
    <div id="an-archetypes"></div>
  </div>
</div>

<div class="page" id="page-sites" style="padding:24px;overflow:auto">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <h2 style="margin:0">Сайты</h2>
    <div>
      <button class="btn btn-ghost btn-sm" onclick="showPage('form')">← Назад</button>
      <button class="btn btn-ghost btn-sm" onclick="loadSitesPage()">↻</button>
      <button class="btn btn-sm" style="background:#a6e3a1;color:#11111b" onclick="openCreateSiteModal()">+ Создать сайт</button>
    </div>
  </div>
  <div id="sites-list" style="display:grid;gap:12px"></div>
</div>

<!-- ══════════ MODAL: CREATE SITE ══════════ -->
<div id="modal-create-site" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#1e1e2e;border:1px solid #313244;border-radius:8px;padding:24px;min-width:420px;max-width:520px">
    <h3 style="margin:0 0 16px 0">Новый сайт</h3>
    <div class="field" style="margin-bottom:12px">
      <label>Домен *</label>
      <input type="text" id="cs-domain" placeholder="tropa.ru">
    </div>
    <div class="field" style="margin-bottom:12px">
      <label>Имя *</label>
      <input type="text" id="cs-name" placeholder="Тропа">
    </div>
    <div class="field" style="margin-bottom:12px">
      <label>Ниша</label>
      <select id="cs-niche"><option value="">— не выбрана —</option></select>
    </div>
    <div class="field" style="margin-bottom:20px">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="cs-istest" style="width:auto">
        Тестовый сайт (исключается из аналитики)
      </label>
    </div>
    <div id="cs-error" style="color:#f38ba8;margin-bottom:12px;display:none"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn btn-ghost btn-sm" onclick="closeCreateSiteModal()">Отмена</button>
      <button class="btn btn-sm" style="background:#a6e3a1;color:#11111b" onclick="submitCreateSite()">Создать</button>
    </div>
  </div>
</div>

<!-- ══════════ MODAL: CREATE AUTHOR ══════════ -->
<div id="modal-create-author" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;align-items:center;justify-content:center">
  <div style="background:#1e1e2e;border:1px solid #313244;border-radius:8px;padding:24px;min-width:480px;max-width:600px;max-height:90vh;overflow:auto">
    <h3 style="margin:0 0 4px 0">Новый автор</h3>
    <div style="color:#6c7086;font-size:12px;margin-bottom:16px" id="ca-site-label"></div>

    <div class="field" style="margin-bottom:12px">
      <label>На основе автора другого сайта в той же нише (необязательно)</label>
      <select id="ca-template"><option value="">— создать с нуля —</option></select>
    </div>

    <div class="field" style="margin-bottom:12px">
      <label>На основе писателя-референса (рекомендуется)</label>
      <select id="ca-reference"><option value="">— без референса —</option></select>
      <div id="ca-reference-status" style="font-size:11px;color:#6c7086;margin-top:4px"></div>
    </div>

    <div class="field" style="margin-bottom:12px">
      <label>Имя / псевдоним *</label>
      <input type="text" id="ca-name" placeholder="Андрей Соколов">
    </div>
    <div class="field" style="margin-bottom:12px">
      <label>Возрастной образ</label>
      <input type="text" id="ca-age" placeholder="около 35 лет">
    </div>
    <div class="field" style="margin-bottom:12px">
      <label>Тон</label>
      <input type="text" id="ca-tone" placeholder="сдержанный, аналитический">
    </div>
    <div class="field" style="margin-bottom:20px">
      <label>Характер</label>
      <textarea id="ca-character" rows="4" placeholder="Опирается на факты и сравнения, любит конкретные цифры…"></textarea>
    </div>

    <div id="ca-error" style="color:#f38ba8;margin-bottom:12px;display:none"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn btn-ghost btn-sm" onclick="closeCreateAuthorModal()">Отмена</button>
      <button class="btn btn-sm" style="background:#a6e3a1;color:#11111b" onclick="submitCreateAuthor()">Создать</button>
    </div>
  </div>
</div>

</div><!-- .page-wrap -->
</div><!-- .app-shell -->
</div><!-- .app -->

<script>
// ── Cost ──────────────────────────────────────────────────────────────────────
function updateCost(article, session, lastCall, total) {
  document.getElementById('c-article').textContent = '$' + article.toFixed(4);
  document.getElementById('c-session').textContent = '$' + session.toFixed(4);
  document.getElementById('c-last').textContent    = '$' + lastCall.toFixed(5);
  document.getElementById('c-total').textContent   = '$' + total.toFixed(4);
  // Подсветка при обновлении
  const el = document.getElementById('c-last');
  el.style.color = '#a6e3a1';
  setTimeout(() => { el.style.color = '#6c7086'; }, 800);
}

// ── WebChannel init ───────────────────────────────────────────────────────────
let bridge = null;
new QWebChannel(qt.webChannelTransport, ch => {
  bridge = ch.objects.bridge;
  // Форма открыта по умолчанию — наполняем dropdown сайтов сразу
  loadSites();
});

const AGENTS = {
  competitor_analysis_agent:{label:'Аналитик конкурентов',role:'analyst',side:'left',model:'Claude Sonnet'},
  brief_agent:              {label:'Стратег ТЗ',          role:'analyst',side:'left',model:'Claude Sonnet'},
  outline_agent:            {label:'Архитектор',          role:'analyst',side:'left',model:'Claude Sonnet'},
  writer_agent:             {label:'Автор текста',        role:'writer', side:'right',model:'Gemini 2.5 Pro'},
  critic_agent:             {label:'Критик',              role:'critic', side:'left', model:'Claude Haiku'},
  editor_agent:             {label:'Редактор',            role:'editor', side:'left', model:'Gemini Flash'},
  final_qa_agent:           {label:'Финальный QA',        role:'qa',     side:'left', model:'Claude Sonnet'},
  metadata_agent:           {label:'Метаданные',          role:'meta',   side:'left', model:'Claude Haiku'},
};

// ── State ─────────────────────────────────────────────────────────────────────
let logCount=0, dlgCount=0, bubId=0;
let serpLoaded_=false;
let pageHistory=[];
let previewOn=false;
let pipelineRunning=false;
let _currentMd='';
let _currentImagesBase='';

// Подменяет относительные пути к картинкам (images/*) на абсолютные file:// URL
// чтобы они корректно отображались в QtWebEngine при предпросмотре.
function rewriteImagePaths(mdText, imagesBase) {
  if (!imagesBase || !mdText) return mdText;
  // ![alt](images/1.webp)  →  ![alt](file:///abs/path/images/1.webp)
  return mdText.replace(
    /(!\[[^\]]*\]\()(images\/[^)\s]+)(\))/g,
    (m, p1, p2, p3) => p1 + imagesBase + p2 + p3
  );
}

// ── Pages ─────────────────────────────────────────────────────────────────────
// Маппинг шагов боковой панели на page-id:
//   home    → form       (форма создания статьи на главной)
//   writing → monitor    (экран генерации)
//   result  → result     (отдельная страница с результатом)
const STEP_TO_PAGE = { home: 'form', writing: 'writing', result: 'result' };
let _hasResult = false;

function showPage(name) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  const el = document.getElementById('page-'+name);
  if (el) el.classList.add('active');
  if (name==='history')   loadHistory();
  if (name==='sites')     loadSitesPage();
  if (name==='analytics') loadAnalyticsPage();

  // Кнопки топбара видимы только на Главной (form).
  // Прямое переключение класса hidden на каждой — надёжнее чем body-класс.
  const isHome = (name === 'form');
  document.querySelectorAll('.tb-home-only').forEach(b => {
    b.classList.toggle('hidden', !isHome);
  });
}

function goToStep(step) {
  // Подсветка активного шага в боковой панели
  ['home','writing','result'].forEach(s=>{
    const ss = document.getElementById('ss-'+s);
    if (ss) ss.classList.toggle('active', s === step);
  });

  if (step === 'home') {
    showPage('form');
    return;
  }

  if (step === 'writing') {
    // Активная или прошедшая генерация → monitor с вкладкой лога
    showPage('monitor');
    if (typeof switchTab === 'function') switchTab('log');
    return;
  }

  if (step === 'result') {
    if (_hasResult) {
      // Результат готов — открываем вкладку результата на monitor
      showPage('monitor');
      if (typeof switchTab === 'function') switchTab('result');
    } else if (pipelineRunning) {
      // Идёт генерация — показываем «в процессе»
      showPage('result');
      document.getElementById('result-empty').style.display = 'none';
      document.getElementById('result-busy').style.display  = '';
    } else {
      // Ничего нет — заглушка
      showPage('result');
      document.getElementById('result-empty').style.display = '';
      document.getElementById('result-busy').style.display  = 'none';
    }
  }
}

// Загружает список сайтов в dropdown формы.
// Тестовые сайты помечаются «(тест)» и выбираются по умолчанию,
// если других сайтов нет.
function loadSites() {
  if (!bridge || !bridge.getSites) {
    // bridge ещё не готов — пробуем ещё раз через момент
    setTimeout(loadSites, 100);
    return;
  }
  bridge.getSites(jsonStr => {
    let sites;
    try { sites = JSON.parse(jsonStr) || []; }
    catch(e) { sites = []; }
    const sel = document.getElementById('f-site');
    if (!sel) return;
    if (!sites.length) {
      sel.innerHTML = '<option value="">— нет сайтов в БД —</option>';
      return;
    }
    // Реальные сайты сверху, тестовые внизу
    const real = sites.filter(s => !s.is_test);
    const test = sites.filter(s => s.is_test);
    const ordered = [...real, ...test];
    sel.innerHTML = ordered.map(s => {
      const label = s.is_test
        ? `${s.domain} — ${s.name} (тест)`
        : `${s.domain} — ${s.name}`;
      return `<option value="${s.domain}">${label}</option>`;
    }).join('');
    // По умолчанию: первый реальный сайт, иначе первый тестовый
    sel.value = ordered[0].domain;
  });
}

// ── Sidebar state ─────────────────────────────────────────────────────────────
// stepDetails[stepId] = [строка, строка, ...] — до 3 деталей на этап
const stepDetails = {};
// sections[title] = {status:'pending'|'running'|'done'|'weak'|'error', iter:0}
const sbSections = {};
let sbSectionOrder = [];   // массив title по порядку из outline
let heroCurrentSec = null;

// Конфигурация этапов — для аккордеона
const STEPS = [
  {id:'input_validation',    label:'Валидация'},
  {id:'serp_analysis',       label:'SERP-анализ'},
  {id:'competitor_analysis', label:'Анализ конкурентов'},
  {id:'brief_generation',    label:'Формирование ТЗ'},
  {id:'outline_generation',  label:'Структура статьи'},
  {id:'section_pipeline',    label:'Генерация секций'},
  {id:'full_draft_assembly', label:'Сборка черновика'},
  {id:'final_qa',            label:'Финальный QA'},
  {id:'metadata_generation', label:'Метаданные'},
  {id:'save_results',        label:'Сохранение'},
];
const STEP_ICONS = {done:'✓',running:'…',error:'✗',weak:'⚠',pending:'·',skipped:'—'};

// Паттерны лога → какой этап это касается
const LOG_STEP_MAP = [
  {re:/SERP/i,                  step:'serp_analysis'},
  {re:/Анализ конкурентов/i,    step:'competitor_analysis'},
  {re:/Формирование ТЗ/i,       step:'brief_generation'},
  {re:/Структура статьи/i,      step:'outline_generation'},
  {re:/Секция \d+\/\d+/,        step:'section_pipeline'},
  {re:/Writer пишет/i,          step:'section_pipeline'},
  {re:/Critic проверяет/i,      step:'section_pipeline'},
  {re:/Editor правит/i,         step:'section_pipeline'},
  {re:/Self-check/i,            step:'section_pipeline'},
  {re:/Секция .+ финальная/i,   step:'section_pipeline'},
  {re:/Сборка статьи/i,         step:'full_draft_assembly'},
  {re:/Финальный QA/i,          step:'final_qa'},
  {re:/Метаданные/i,            step:'metadata_generation'},
  {re:/Сохранени/i,             step:'save_results'},
];

// Паттерны → Hero
const HERO_PATTERNS = [
  {re:/Writer пишет '(.+?)'/,                      agent:'Writer',    mk:(m)=>['Пишет секцию', m[1]]},
  {re:/Critic проверяет '(.+?)' \(итерация (\d+)\)/,agent:'Critic',   mk:(m)=>[`Проверяет · итер. ${m[2]}`, m[1]]},
  {re:/Editor правит '(.+?)'/,                     agent:'Editor',    mk:(m)=>['Правит секцию', m[1]]},
  {re:/Self-check '(.+?)'/,                        agent:'Writer',    mk:(m)=>['Self-check', m[1]]},
  {re:/Self-check пройден/,                        agent:'Writer',    mk:(m)=>['Self-check ✓', '']},
  {re:/Анализ конкурентов/i,                       agent:'Аналитик',  mk:(m)=>['Анализ конкурентов','']},
  {re:/Формирование ТЗ/i,                          agent:'Стратег',   mk:(m)=>['Формирует ТЗ','']},
  {re:/Структура статьи/i,                         agent:'Архитектор',mk:(m)=>['Строит структуру','']},
  {re:/Финальный QA/i,                             agent:'QA',        mk:(m)=>['Финальный QA','']},
  {re:/Метаданные/i,                               agent:'Мета',      mk:(m)=>['Генерирует метаданные','']},
  {re:/Сборка статьи/i,                            agent:'Система',   mk:(m)=>['Собирает черновик','']},
  {re:/Сохранение/i,                               agent:'Система',   mk:(m)=>['Сохранение результатов','']},
  {re:/SERP/i,                                     agent:'SERP',      mk:(m)=>['Загрузка SERP','']},
];

// Паттерны секций → обновление статуса
const SEC_STATUS_PATTERNS = [
  {re:/Секция '(.+?)' финальная/,    status:'done'},
  {re:/Секция '(.+?)' — источники/,  status:'done'},
  {re:/⚠ Секция не прошла/,          status:'weak', useCurrent:true},
  {re:/Writer пишет '(.+?)'/,        status:'running'},
  {re:/Critic проверяет '(.+?)'/,    status:'running', getIter:/\(итерация (\d+)\)/},
  {re:/Editor правит '(.+?)'/,       status:'running'},
  {re:/Self-check '(.+?)'/,          status:'running'},
];

// ── Init steps flat list ──────────────────────────────────────────────────────
function initSteps() {
  const c = document.getElementById('steps-container');
  c.innerHTML = '';
  STEPS.forEach(s => {
    stepDetails[s.id] = [];
    const item = document.createElement('div');
    item.className = 'step-item';
    item.id = 'stepitem-' + s.id;
    item.innerHTML = `
      <div class="step-hdr">
        <div class="step-ic" id="ic-${s.id}">·</div>
        <div class="step-tx" id="tx-${s.id}">${s.label}</div>
      </div>
      <div class="step-events" id="det-${s.id}" style="display:none"></div>`;
    c.appendChild(item);
  });
}

function setStepStatus(id, status) {
  const ic = document.getElementById('ic-'+id);
  const tx = document.getElementById('tx-'+id);
  if (!ic) return;
  ic.className = 'step-ic ' + status;
  ic.textContent = STEP_ICONS[status]||'·';
  tx.className = 'step-tx ' + status;
  // Скрываем события у завершённых шагов, показываем у текущего
  const det = document.getElementById('det-'+id);
  if (det) det.style.display = status === 'running' ? '' : 'none';
}

function addStepDetail(stepId, msg) {
  if (!stepDetails[stepId]) stepDetails[stepId] = [];
  stepDetails[stepId].push(msg);
  if (stepDetails[stepId].length > 3) stepDetails[stepId].shift();
  const det = document.getElementById('det-'+stepId);
  if (!det) return;
  det.style.display = '';
  const lines = stepDetails[stepId];
  det.innerHTML = lines.map((l, i) =>
    `<div class="step-event ${i===lines.length-1?'fresh':''}">${esc(l.slice(0,44))}${l.length>44?'…':''}</div>`
  ).join('');
}

// ── Hero ──────────────────────────────────────────────────────────────────────
function setHero(agent, action, detail, dotStatus) {
  const dot = document.getElementById('hero-dot');
  const agEl = document.getElementById('hero-agent');
  const acEl = document.getElementById('hero-action');
  const dtEl = document.getElementById('hero-detail');
  if (!dot) return;
  dot.className = 'sb-hero-dot ' + (dotStatus||'');
  agEl.textContent = agent || 'Система';
  acEl.textContent = action || '—';
  dtEl.textContent = detail || '';
}

// ── Sections ──────────────────────────────────────────────────────────────────
function initSectionPlan(titles) {
  // Инициализируем все секции сразу из outline
  sbSectionOrder = titles;
  titles.forEach(t => {
    sbSections[t] = {status:'pending', iter:0};
  });
  document.getElementById('sb-sections').style.display = '';
  const cnt = document.getElementById('sec-count');
  if (cnt) cnt.textContent = `0/${titles.length}`;
  renderSecList();
}

function updateSecStatus(title, status, iter) {
  if (!sbSections[title]) return;
  sbSections[title].status = status;
  if (iter !== undefined) sbSections[title].iter = iter;
  updateSecProgress();
  renderSecList();
}

function updateSecProgress() {
  const total = sbSectionOrder.length;
  const done = sbSectionOrder.filter(t =>
    sbSections[t] && (sbSections[t].status==='done'||sbSections[t].status==='weak')
  ).length;
  const bar = document.getElementById('sec-pbar');
  const cnt = document.getElementById('sec-count');
  if (bar) bar.style.width = total ? Math.round(done/total*100)+'%' : '0%';
  if (cnt) cnt.textContent = `${done}/${total}`;
}

function renderSecList() {
  const el = document.getElementById('sec-list');
  if (!el) return;
  const IC = {done:'✓', running:'…', weak:'⚠', error:'✗', pending:'·'};
  const COLORS = {done:'#a6e3a1', running:'#89b4fa', weak:'#fab387', error:'#f38ba8', pending:'#45475a'};
  el.innerHTML = sbSectionOrder.map(title => {
    const s = sbSections[title] || {status:'pending', iter:0};
    const ic = IC[s.status]||'·';
    const col = COLORS[s.status]||'#45475a';
    const iterStr = s.status==='running'&&s.iter>0 ? ` ·${s.iter}` : '';
    return `<div class="sec-row ${s.status==='running'?'active':''}">
      <span class="sec-ic" style="color:${col}">${ic}</span>
      <span class="sec-name ${s.status}">${esc(title)}</span>
      ${iterStr?`<span class="sec-iter">${iterStr}</span>`:''}
    </div>`;
  }).join('');
  const active = el.querySelector('.sec-row.active');
  if (active) active.scrollIntoView({block:'nearest'});
}

// ── Main log processor → sidebar ──────────────────────────────────────────────
function sidebarOnLog(msg) {
  // Скрытый сигнал от Python со списком секций
  if (msg.startsWith('__SECTIONS_PLAN__:')) {
    try {
      const titles = JSON.parse(msg.slice(18));
      initSectionPlan(titles);
    } catch(e){}
    return; // не добавляем в лог
  }

  // Определяем к какому этапу относится сообщение
  let targetStep = null;
  for (const p of LOG_STEP_MAP) {
    if (p.re.test(msg)) { targetStep = p.step; break; }
  }
  if (targetStep) {
    addStepDetail(targetStep, msg);
  }

  // Обновляем Hero
  for (const p of HERO_PATTERNS) {
    const m = msg.match(p.re);
    if (m) {
      const [action, detail] = p.mk(m);
      setHero(p.agent, action, detail, 'running');
      break;
    }
  }

  // Обновляем статус секции
  for (const p of SEC_STATUS_PATTERNS) {
    const m = msg.match(p.re);
    if (m) {
      const title = p.useCurrent ? heroCurrentSec : m[1];
      if (title && sbSections[title] !== undefined) {
        let iter = undefined;
        if (p.getIter) {
          const im = msg.match(p.getIter);
          if (im) iter = parseInt(im[1]);
        }
        if (title) heroCurrentSec = title;
        updateSecStatus(title, p.status, iter);
        if (p.status === 'done' || p.status === 'weak') {
          setHero('', '', '', p.status);
        }
      }
      break;
    }
  }
}

function resetSidebar() {
  Object.keys(sbSections).forEach(k => delete sbSections[k]);
  sbSectionOrder.length = 0;
  heroCurrentSec = null;
  setHero('Система', 'Запуск пайплайна', '', 'running');
  document.getElementById('sb-sections').style.display = 'none';
  const bar = document.getElementById('sec-pbar');
  if (bar) bar.style.width = '0%';
  const cnt = document.getElementById('sec-count');
  if (cnt) cnt.textContent = '0/0';
  const sl = document.getElementById('sec-list');
  if (sl) sl.innerHTML = '';
}


function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+name));
  const sw = document.getElementById('pv-switcher');
  sw.style.display = name==='result' ? 'flex' : 'none';
}

// ── Log ───────────────────────────────────────────────────────────────────────
function appendLog(msg, type='') {
  // Скрытый сигнал — не показываем в логе
  if (msg.startsWith('__SECTIONS_PLAN__:')) { sidebarOnLog(msg); return; }
  const t = new Date().toTimeString().slice(0,8);
  const el = document.createElement('div');
  el.className = 'log-line';
  el.innerHTML = `<span class="log-t">${t}</span><span class="log-m ${type}">${esc(msg)}</span>`;
  document.getElementById('log-list').appendChild(el);
  logCount++;
  document.getElementById('cnt-log').textContent = logCount;
  el.scrollIntoView({behavior:'smooth',block:'nearest'});
  sidebarOnLog(msg);
}

// ── Dialog ────────────────────────────────────────────────────────────────────
function appendDialog(step, prompt, response) {
  const ag = AGENTS[step]||{label:step,role:'analyst',side:'left',model:''};
  const now = new Date().toTimeString().slice(0,8);
  const id = 'b'+(++bubId);
  const pLines = prompt.trim().split('\n');
  const pShort = esc(pLines.slice(0,5).join('\n'));
  const more = pLines.length>5 ? `\n... ещё ${pLines.length-5} строк` : '';
  const row = document.createElement('div');
  row.className = `msg-row ${ag.side} ${ag.role}`;
  row.innerHTML = `
    <div class="msg-lbl role-${ag.role}">${ag.label}</div>
    <div class="bubble">
      <div class="prompt-tog" onclick="togPrompt('${id}')"><span id="arr-${id}">▸</span> Промпт</div>
      <div class="prompt-body" id="pr-${id}">${pShort}${more}</div>
      <div class="resp-body">${md(response)}</div>
    </div>
    <div class="bub-meta"><span class="bub-model">${ag.model}</span><span class="bub-time">${now}</span></div>`;
  document.getElementById('dialog-list').appendChild(row);
  dlgCount++;
  document.getElementById('cnt-dlg').textContent = dlgCount;
  row.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function togPrompt(id) {
  const b=document.getElementById('pr-'+id);
  const a=document.getElementById('arr-'+id);
  a.textContent = b.classList.toggle('open')?'▾':'▸';
}

// ── Result ────────────────────────────────────────────────────────────────────
// ── QA Criteria визуализация ──────────────────────────────────────────────────
const QA_CRITERIA_META = [
  {key:'brief_alignment', label:'Brief alignment', code:false, weight:0.20},
  {key:'completeness',    label:'Completeness',    code:true,  weight:0.20},
  {key:'intent_coverage', label:'Intent coverage', code:false, weight:0.15},
  {key:'keyword_usage',   label:'Keywords',        code:true,  weight:0.10},
  {key:'lsi_coverage',    label:'LSI coverage',    code:true,  weight:0.05},
  {key:'readability',     label:'Readability',     code:true,  weight:0.10},
  {key:'structure',       label:'Structure',       code:true,  weight:0.10},
  {key:'factuality',      label:'Factuality',      code:false, weight:0.05},
  {key:'length_control',  label:'Length control',  code:true,  weight:0.05},
];

function buildQaCriteria(qa) {
  const scores = qa.criteria_scores || {};
  if (!Object.keys(scores).length) return '';

  const rows = QA_CRITERIA_META.map(m => {
    const v = Math.round(scores[m.key] ?? 0);
    const color = v >= 85 ? '#1D9E75' : v >= 70 ? '#BA7517' : '#E24B4A';
    const typeClass = m.code ? 'code' : 'llm';
    const typeLabel = m.code ? 'код' : 'llm';
    const weightLabel = `×${Math.round(m.weight*100)}%`;
    return `<div class="qa-crit-row ${typeClass}">
      <div class="qa-crit-label">${m.label} <span style="color:#45475a">${weightLabel}</span></div>
      <div class="qa-crit-bar-wrap">
        <div class="qa-crit-bar" style="width:${v}%"></div>
      </div>
      <div class="qa-crit-val" style="color:${color}">${v}</div>
      <div class="qa-crit-type">${typeLabel}</div>
    </div>`;
  }).join('');

  return `<div class="qa-criteria-card">
    <div class="qa-criteria-title">Детализация оценки</div>
    ${rows}
    <div class="qa-legend">
      <div class="qa-leg-item">
        <div class="qa-leg-dot" style="background:#1D9E75"></div>Считается кодом
      </div>
      <div class="qa-leg-item">
        <div class="qa-leg-dot" style="background:#f38ba8"></div>Оценивает LLM
      </div>
    </div>
  </div>`;
}

function setResult(data) {
  if (!data) return;
  const {pkg, qa} = data;
  const score = qa.score||0;
  const sc = score>=85?'#a6e3a1':score>=75?'#f9e2af':'#f38ba8';
  const statusLabel = score>=85?'PASS':score>=75?'PASS WITH WARNINGS':'FAIL';
  const warns = (qa.warnings||[]).map(w=>`<div class="warn-item">${esc(w)}</div>`).join('');
  const mdTxt = pkg.article_markdown||'';
  const mdPreview = pkg.article_markdown_preview || mdTxt;
  document.getElementById('result-content').innerHTML = `
    <div class="res-hdr">
      <div class="qa-circle" style="border-color:${sc}">
        <div class="qa-num" style="color:${sc}">${score}</div>
        <div class="qa-lbl">/ 100</div>
      </div>
      <div>
        <div class="res-status" style="color:${sc}">${statusLabel}</div>
        <div class="res-rec">${esc(qa.recommendation||'')}</div>
      </div>
    </div>
    ${buildQaCriteria(qa)}
    ${warns?`<div class="warn-box">${warns}</div>`:''}
    <div class="res-fields">
      ${frow('slug',pkg.slug)}${frow('meta title',pkg.meta_title)}
      ${frow('meta description',pkg.meta_description)}
      ${frow('теги',(pkg.tags||[]).join(', '))}
    </div>
    <div class="pv-body">
      <div id="pv-md-el" class="pv-raw">${esc(mdTxt)}</div>
      <div id="pv-rendered-el" class="pv-rendered" style="display:none">${renderMd(mdPreview)}</div>
    </div>`;
  previewOn = false;
  updatePreviewBtn();
  _currentMd = mdTxt;
  switchTab('result');
  document.getElementById('btn-folder').style.display='';
  document.getElementById('btn-copy').style.display='';
}

function togglePreview() {
  previewOn = !previewOn;
  updatePreviewBtn();
  const md = document.getElementById('pv-md-el');
  const rv = document.getElementById('pv-rendered-el');
  if (md) md.style.display = previewOn ? 'none' : '';
  if (rv) rv.style.display = previewOn ? '' : 'none';
}

function updatePreviewBtn() {
  const btn = document.getElementById('btn-preview-toggle');
  if (!btn) return;
  if (previewOn) {
    btn.textContent = 'Предпросмотр вкл';
    btn.style.background = '#a6e3a1';
    btn.style.color = '#1e1e2e';
  } else {
    btn.textContent = 'Предпросмотр';
    btn.style.background = '';
    btn.style.color = '';
  }
}

// ── History ───────────────────────────────────────────────────────────────────
function loadHistory() {
  if (!bridge) { setTimeout(loadHistory, 200); return; }
  const el = document.getElementById('hist-items');
  el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  // QWebChannel: синхронный return недоступен — используем runJavaScript через Python
  // Вызываем getArticles и получаем результат через callback
  bridge.getArticles(function(raw) {
    let articles = [];
    try { articles = JSON.parse(raw); } catch(e){}
    const STATUS_ICON = {
      completed:'✓', ready_for_manual_review:'✓',
      ready_for_manual_review_with_warnings:'⚠',
      failed:'✗', stopped_by_user:'■',
      sections_in_progress:'⏳', draft_ready:'⏳',
    };
    if (!articles.length) {
      el.innerHTML = '<div class="empty-state">Нет статей в истории</div>';
      return;
    }
    el.innerHTML = articles.map(a => {
      const score = parseInt(a.qa_score)||0;
      const badgeCls = score>=70?'hbadge-pass':score>=50?'hbadge-warn':'hbadge-fail';
      const scoreStr = a.qa_score!=null ? `<span class="hbadge ${badgeCls}">${score}/100</span>` : '';
      const icon = STATUS_ICON[a.status]||'•';
      const title = (a.title||'Без названия').slice(0,45);
      const date = a.created_at ? new Date(a.created_at).toLocaleString('ru') : '';
      const aid = esc(a.article_id);
      return `<div class="hist-item" onclick="showHistDetail('${aid}',this)">
        <div class="hist-item-title">${icon} ${esc(title)}</div>
        <div class="hist-item-meta"><span class="hist-item-date">${date}</span>${scoreStr}</div>
      </div>`;
    }).join('');
  });
}

function showHistDetail(article_id, el) {
  document.querySelectorAll('.hist-item').forEach(e=>e.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('hist-empty').style.display='none';
  const det = document.getElementById('hist-detail');
  det.style.display='block';
  det.innerHTML='<div class="empty-state">Загрузка...</div>';
  // Сбрасываем кнопку копирования пока грузим
  _currentMd = '';
  document.getElementById('btn-copy').style.display='none';
  if (!bridge) return;
  bridge.getArticleResult(article_id, function(raw) {
    try {
      const data = JSON.parse(raw);
      if (data) {
        det.innerHTML = buildResultHtml(data, article_id);
        _currentMd = data.pkg.article_markdown || '';
        if (_currentMd) {
          document.getElementById('btn-copy').style.display='';
        }
        return;
      }
    } catch(e){}
    det.innerHTML='<div class="empty-state">Результат недоступен</div>';
  });
}

function buildResultHtml(data, article_id) {
  const {pkg,qa} = data;
  const score = qa.score||0;
  const sc = score>=85?'#a6e3a1':score>=75?'#f9e2af':'#f38ba8';
  const statusLabel = score>=85?'PASS':score>=75?'PASS WITH WARNINGS':'FAIL';
  const warns = (qa.warnings||[]).map(w=>`<div class="warn-item">${esc(w)}</div>`).join('');
  const mdTxt = pkg.article_markdown||'';
  const mdPreview = pkg.article_markdown_preview || mdTxt;
  const uid = 'h'+Math.random().toString(36).slice(2,7);
  return `
    <div class="res-hdr">
      <div class="qa-circle" style="border-color:${sc}">
        <div class="qa-num" style="color:${sc}">${score}</div>
        <div class="qa-lbl">/ 100</div>
      </div>
      <div>
        <div class="res-status" style="color:${sc}">${statusLabel}</div>
        <div class="res-rec">${esc(qa.recommendation||'')}</div>
      </div>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto"
        onclick="bridge&&bridge.openArticleFolder('${article_id}')">Открыть папку</button>
    </div>
    ${buildQaCriteria(qa)}
    ${warns?`<div class="warn-box">${warns}</div>`:''}
    <div class="res-fields">
      ${frow('slug',pkg.slug)}${frow('meta title',pkg.meta_title)}
      ${frow('meta description',pkg.meta_description)}
      ${frow('теги',(pkg.tags||[]).join(', '))}
    </div>
    <div style="margin-bottom:10px">
      <button class="pv-btn" id="hpvbtn-${uid}" onclick="hTogglePv('${uid}')">Предпросмотр</button>
    </div>
    <div class="pv-body">
      <div id="hpvmd-${uid}" class="pv-raw">${esc(mdTxt)}</div>
      <div id="hpvrv-${uid}" class="pv-rendered" style="display:none">${renderMd(mdPreview)}</div>
    </div>`;
}

function hTogglePv(uid) {
  const md  = document.getElementById('hpvmd-'+uid);
  const rv  = document.getElementById('hpvrv-'+uid);
  const btn = document.getElementById('hpvbtn-'+uid);
  const on  = rv.style.display !== 'none';
  md.style.display  = on ? '' : 'none';
  rv.style.display  = on ? 'none' : '';
  if (on) {
    btn.textContent = 'Предпросмотр';
    btn.style.background = ''; btn.style.color = '';
  } else {
    btn.textContent = 'Предпросмотр вкл';
    btn.style.background = '#a6e3a1'; btn.style.color = '#1e1e2e';
  }
}

// ── Pipeline UI state ─────────────────────────────────────────────────────────
function uiPipelineStarted() {
  logCount=0; dlgCount=0; bubId=0;
  document.getElementById('log-list').innerHTML='';
  document.getElementById('dialog-list').innerHTML='';
  document.getElementById('result-content').innerHTML='<div class="empty-state">Результат появится после завершения пайплайна</div>';
  document.getElementById('cnt-log').textContent='0';
  document.getElementById('cnt-dlg').textContent='0';
  document.getElementById('btn-stop').style.display='';
  document.getElementById('btn-folder').style.display='none';
  document.getElementById('topbar-status').textContent='Выполняется…';
  document.getElementById('ss-writing').classList.add('busy');
  _hasResult = false;
  pipelineRunning = true;
  updateNewArticleBtn();
  initSteps();
  resetSidebar();
  showPage('monitor');
  switchTab('log');
  setFormLocked(true);
}

function uiPipelineDone(score) {
  document.getElementById('btn-stop').style.display='none';
  document.getElementById('topbar-status').textContent=`Завершено: ${score}/100`;
  document.getElementById('ss-writing').classList.remove('busy');
  _hasResult = true;
  // Автопереход на «Результат»
  goToStep('result');
  setHero('Система', 'Пайплайн завершён', `QA: ${score}/100`, 'done');
  pipelineRunning = false;
  updateNewArticleBtn();
  setFormLocked(false);
}

function uiPipelineError() {
  document.getElementById('btn-stop').style.display='none';
  document.getElementById('topbar-status').textContent='Ошибка';
  pipelineRunning = false;
  updateNewArticleBtn();
  setFormLocked(false);
}

function updateNewArticleBtn() {
  const btn = document.getElementById('btn-new-article');
  if (!btn) return;
  if (pipelineRunning) {
    btn.textContent = '← К генерации';
    btn.style.background = '#1a2a3a';
    btn.style.color = '#89b4fa';
    btn.style.fontWeight = '600';
  } else {
    btn.textContent = '+ Новая статья';
    btn.style.background = '';
    btn.style.color = '';
    btn.style.fontWeight = '';
  }
}

function setFormLocked(locked) {
  ['f-title','f-mainkey','f-geo','f-seckeys','f-words','f-lang','f-intent',
   'f-type','f-difficulty','f-style','f-forbidden','f-notes','f-refresh-serp'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.disabled=locked;
  });
  document.getElementById('btn-run').disabled=locked;
  document.getElementById('btn-validate').disabled=locked;
}

// ── SERP ──────────────────────────────────────────────────────────────────────
function handleSerpClick() {
  if (serpLoaded_) return;
  if (!bridge) {
    setTimeout(handleSerpClick, 300);
    return;
  }
  bridge.browseSerp();
}

function serpLoaded(fname, count, sizeKb, secondaryKeys) {
  serpLoaded_=true;
  document.getElementById('serp-empty').style.display='none';
  document.getElementById('serp-loaded').style.display='block';
  document.getElementById('serp-fname').textContent=fname;
  document.getElementById('serp-meta').textContent=`${count} результатов · ${sizeKb} KB`;
  document.getElementById('serp-zone').classList.add('loaded');
  if (secondaryKeys&&secondaryKeys.length)
    document.getElementById('f-seckeys').value=secondaryKeys.join('\n');
}

function clearSerp() {
  serpLoaded_=false;
  if (bridge) bridge.onClearSerp();
  document.getElementById('serp-empty').style.display='block';
  document.getElementById('serp-loaded').style.display='none';
  document.getElementById('serp-zone').classList.remove('loaded');
}

// ── Form actions ──────────────────────────────────────────────────────────────
function collectForm() {
  const elems=[];
  if(document.getElementById('chk-faq').checked)     elems.push('faq');
  if(document.getElementById('chk-quick').checked)   elems.push('quick_answer');
  if(document.getElementById('chk-table').checked)   elems.push('table');
  if(document.getElementById('chk-list').checked)    elems.push('list');
  if(document.getElementById('chk-concl').checked)   elems.push('conclusion');
  if(document.getElementById('chk-sources').checked) elems.push('sources_block');
  return {
    site_domain:            document.getElementById('f-site').value,
    article_title:          document.getElementById('f-title').value.trim(),
    main_keyword:           document.getElementById('f-mainkey').value.trim(),
    secondary_keywords:     document.getElementById('f-seckeys').value,
    length_strategy:        (document.querySelector('input[name="length-strategy"]:checked')||{}).value || 'match_top',
    target_word_count:      _getStrategyWords(),
    language:               document.getElementById('f-lang').value,
    geo:                    document.getElementById('f-geo').value.trim(),
    intent:                 document.getElementById('f-intent').value,
    article_type:           document.getElementById('f-type').value,
    difficulty:             document.getElementById('f-difficulty').value,
    style_archetype:        document.getElementById('f-style').value,
    forbidden_words:        document.getElementById('f-forbidden').value,
    required_elements:      elems.length?elems:['conclusion'],
    optional_notes:         document.getElementById('f-notes').value.trim(),
    always_review_sections: document.getElementById('chk-always-review').checked,
    force_refresh_serp:     document.getElementById('f-refresh-serp').checked,
  };
}

function _getStrategyWords() {
  const s = (document.querySelector('input[name="length-strategy"]:checked')||{}).value;
  if (s !== 'custom') return null;
  const v = parseInt(document.getElementById('f-words').value);
  return isFinite(v) && v > 0 ? v : null;
}

function onStrategyChange() {
  const s = (document.querySelector('input[name="length-strategy"]:checked')||{}).value;
  const wrap = document.getElementById('f-words-wrap');
  if (wrap) wrap.style.display = (s === 'custom') ? '' : 'none';
}

function onRunClicked() {
  if (!bridge) return;
  const d=collectForm();
  if (!d.site_domain){alert('Выберите сайт');return;}
  if (!d.article_title){alert('Введите название статьи');return;}
  if (!d.main_keyword){alert('Введите главный ключ');return;}
  bridge.runPipeline(JSON.stringify(d));
}

function onValidateClicked() {
  if (bridge) bridge.validateForm(JSON.stringify(collectForm()));
}

function fillDemo() {
  document.getElementById('f-title').value   = 'Озеро Байкал где находится 🌊 Глубина, координаты и факты';
  document.getElementById('f-mainkey').value = 'байкал где находится';
  document.getElementById('f-geo').value     = 'Россия';
  document.getElementById('f-seckeys').value = [
    'байкал дно',
    'где находится байкал',
    'озеро байкал где находится',
    'байкал глубина',
    'где байкал',
    'географические координаты озера байкал',
    'озеро байкал глубина',
    'байкал: где находится',
    'описание озера байкал',
    'байкал в каком городе',
    'байкал где',
    'в каком городе находится байкал',
    'озера байкал',
    'что такое байкал',
    'байкал какой город',
    'байкал площадь',
    'дно озера байкал',
    'какая глубина озера байкал',
    'максимальная глубина озера байкал',
    'размеры озера байкал',
    'сколько лет озеру байкал',
  ].join('\n');
  document.getElementById('f-words').value      = 1200;
  const matchRadio = document.querySelector('input[name="length-strategy"][value="match_top"]');
  if (matchRadio) matchRadio.checked = true;
  onStrategyChange();
  document.getElementById('f-lang').value       = 'ru';
  document.getElementById('f-intent').value     = '';
  document.getElementById('f-type').value       = 'informational';
  document.getElementById('f-difficulty').value = 'medium';
  document.getElementById('f-style').value      = 'expert_clear';
  document.getElementById('f-forbidden').value  = '';
  document.getElementById('f-notes').value      = '';
  // Все обязательные элементы
  document.getElementById('chk-faq').checked     = true;
  document.getElementById('chk-quick').checked   = true;
  document.getElementById('chk-table').checked   = true;
  document.getElementById('chk-list').checked    = true;
  document.getElementById('chk-concl').checked   = true;
  document.getElementById('chk-sources').checked = true;
  document.getElementById('chk-always-review').checked = true;
  document.getElementById('f-refresh-serp').checked    = false;
}

function clearForm() {
  ['f-title','f-mainkey','f-geo','f-seckeys','f-forbidden','f-notes'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.value='';
  });
  document.getElementById('f-words').value=1200;
  const matchRadio2 = document.querySelector('input[name="length-strategy"][value="match_top"]');
  if (matchRadio2) matchRadio2.checked = true;
  onStrategyChange();
  document.getElementById('f-lang').value='ru';
  document.getElementById('f-intent').value='';
  document.getElementById('f-type').value='informational';
  document.getElementById('f-difficulty').value='medium';
  document.getElementById('f-style').value='expert_clear';
  document.getElementById('chk-faq').checked=true;
  document.getElementById('chk-quick').checked=true;
  document.getElementById('chk-table').checked=false;
  document.getElementById('chk-list').checked=false;
  document.getElementById('chk-concl').checked=true;
  document.getElementById('chk-sources').checked=false;
  document.getElementById('chk-always-review').checked=true;
  document.getElementById('f-refresh-serp').checked=false;
  clearSerp();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(t){
  return String(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function md(t){
  return esc(t).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/\*(.+?)\*/g,'<i>$1</i>')
    .replace(/`(.+?)`/g,'<code>$1</code>').replace(/^#{1,4}\s+(.+)$/gm,'<b>$1</b>')
    .replace(/\n/g,'<br>');
}
function renderMd(text) {
  if (typeof marked !== 'undefined') {
    try {
      marked.setOptions({breaks:true, gfm:true});
      return marked.parse(text);
    } catch(e){}
  }
  // Fallback если marked не загрузился
  return esc(text)
    .replace(/^# (.+)$/gm,'<h1>$1</h1>').replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>').replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>').replace(/`(.+?)`/g,'<code>$1</code>')
    .replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>');
}

// ── Копировать статью ─────────────────────────────────────────────────────────
function copyArticle() {
  if (!_currentMd || !bridge) return;
  bridge.copyToClipboard(_currentMd);
  const btn = document.getElementById('btn-copy');
  if (!btn) return;
  const orig = btn.textContent;
  btn.textContent = 'Скопировано ✓';
  btn.style.color = '#a6e3a1';
  setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 2000);
}

// ── Review Panel ──────────────────────────────────────────────────────────────
let _reviewOutlineSections = [];
let _reviewArchetype = null;          // {suggested_id, suggested_info, niche_id, alternatives}
let _reviewChosenArchetypeId = null;  // итоговый выбор юзера (по умолчанию = suggested)
let _reviewGaps = [];        // полный список gaps из данных конкурентов
let _selectedGapIdx = new Set();  // индексы выбранных gaps
let _dragSrcIdx = null;

function showReviewPanel(data) {
  const c = data.competitor;
  const o = data.outline;

  _reviewGaps = c.content_gaps || [];
  _selectedGapIdx = new Set();

  // Статистика конкурентов
  const maxFreq = Math.max(...(c.common_h2_titles||[]).map(t=>t.frequency), 1);
  document.getElementById('review-competitor-stats').innerHTML = `
    <div class="stat-block">
      <div class="stat-label">Объём статей (слов)</div>
      <div class="stat-values">${(c.word_count_per_page||[]).join(', ') || '—'}</div>
      <div class="stat-rec">Рекомендация AI: ${c.word_count_avg} слов</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">Количество H2 блоков</div>
      <div class="stat-values">${(c.h2_per_page||[]).join(', ') || '—'}</div>
      <div class="stat-rec">Рекомендация AI: ${c.h2_avg} блоков</div>
    </div>`;

  document.getElementById('review-h2-titles').innerHTML =
    (c.common_h2_titles||[]).slice(0,10).map(t => {
      const pct = Math.round(t.frequency/maxFreq*100);
      return `<div class="h2-title-row">
        <div style="flex:1">
          <div class="h2-title-name">${esc(t.title)}</div>
          <div class="h2-title-bar" style="width:${pct}%"></div>
        </div>
        <div class="h2-title-freq">${t.frequency}/${maxFreq}</div>
      </div>`;
    }).join('') || '<div style="color:#45475a;font-size:11px">Нет данных</div>';

  document.getElementById('review-must-have').innerHTML =
    (c.must_have_topics||[]).map(t =>
      `<div style="font-size:11px;color:#a6adc8;padding:2px 0">• ${esc(t)}</div>`
    ).join('') || '<div style="color:#45475a;font-size:11px">—</div>';

  document.getElementById('review-gaps').innerHTML =
    (c.content_gaps||[]).map((g, i) => {
      const title = typeof g === 'string' ? g : (g.title || '');
      const desc  = typeof g === 'string' ? '' : (g.description || '');
      const after = typeof g === 'string' ? '' : (g.after_section || 'в конец');
      const words = typeof g === 'string' ? 200 : (g.word_count || 200);
      return `<div class="gap-item" id="gap-item-${i}" onclick="toggleGap(${i})">
        <div class="gap-item-row">
          <input type="checkbox" class="gap-cb" id="gap-cb-${i}"
            onclick="event.stopPropagation();toggleGap(${i})">
          <div class="gap-content">
            <div class="gap-title">${esc(title)}</div>
            ${desc ? `<div class="gap-desc">${esc(desc)}</div>` : ''}
            <div class="gap-meta">
              ${after ? `<span class="gap-after">↳ после «${esc(after)}»</span>` : ''}
              <span class="gap-words">${words} слов</span>
            </div>
          </div>
        </div>
      </div>`;
    }).join('') || '<div style="color:#45475a;font-size:11px">—</div>';

  // H1
  document.getElementById('outline-h1').value = o.h1 || '';

  // Архетип
  _reviewArchetype = data.archetype || {};
  _reviewChosenArchetypeId = _reviewArchetype.suggested_id || null;
  renderArchetypeBlock();

  // Секции
  _reviewOutlineSections = (o.sections||[]).map(s => ({...s}));
  renderSecEditor();

  document.getElementById('review-overlay').classList.add('active');
}

function hideReviewPanel() {
  document.getElementById('review-overlay').classList.remove('active');
}

function renderArchetypeBlock() {
  const box = document.getElementById('review-archetype');
  if (!box) return;
  const a = _reviewArchetype || {};

  // Случай 1: автоподбор не сработал (нет ниши у сайта)
  if (!a.suggested_id || !a.suggested_info) {
    if (!a.niche_id) {
      box.innerHTML = '<div style="color:#6c7086;font-size:12px">'
        + 'Архетип не подобран: у сайта не задана ниша. '
        + 'Привяжите нишу к сайту, чтобы получать предложения.'
        + '</div>';
    } else {
      box.innerHTML = '<div style="color:#6c7086;font-size:12px">'
        + 'Автоподбор не нашёл подходящего архетипа. Выберите вручную:'
        + '</div>'
        + buildArchetypeSelect(a.alternatives, null);
    }
    return;
  }

  // Случай 2: предложение есть — показываем карточку + dropdown альтернатив
  const info = a.suggested_info;
  const isChanged = _reviewChosenArchetypeId !== a.suggested_id;
  box.innerHTML = `
    <div style="display:flex;align-items:flex-start;gap:10px">
      <div style="flex:1;min-width:0">
        <div style="font-size:11px;color:#6c7086;margin-bottom:2px">
          ${isChanged ? 'Изменён вручную' : 'Предложено системой'}
        </div>
        <div style="font-weight:600">${esc(currentArchetypeName())}</div>
        <div style="font-size:11px;color:#a6adc8;margin-top:4px">${esc(currentArchetypeDescription())}</div>
      </div>
    </div>
    <div style="margin-top:10px">
      <label style="font-size:11px;color:#6c7086;display:block;margin-bottom:4px">Изменить архетип:</label>
      ${buildArchetypeSelect(a.alternatives, _reviewChosenArchetypeId)}
    </div>
  `;
}

function buildArchetypeSelect(alternatives, currentId) {
  const opts = (alternatives || []).map(a =>
    `<option value="${a.archetype_id}" ${a.archetype_id===currentId?'selected':''}>${esc(a.name_ru)}</option>`
  ).join('');
  return `<select onchange="onArchetypeChange(this.value)" style="width:100%">${opts}</select>`;
}

function currentArchetypeName() {
  const a = _reviewArchetype || {};
  const chosen = _reviewChosenArchetypeId;
  if (a.suggested_id === chosen && a.suggested_info) {
    return a.suggested_info.name_ru;
  }
  const alt = (a.alternatives || []).find(x => x.archetype_id === chosen);
  return alt ? alt.name_ru : (chosen || '—');
}

function currentArchetypeDescription() {
  const a = _reviewArchetype || {};
  const chosen = _reviewChosenArchetypeId;
  if (a.suggested_id === chosen && a.suggested_info) {
    return a.suggested_info.description || '';
  }
  const alt = (a.alternatives || []).find(x => x.archetype_id === chosen);
  return alt ? (alt.description || '') : '';
}

function onArchetypeChange(newId) {
  _reviewChosenArchetypeId = newId || null;
  renderArchetypeBlock();
}

function renderSecEditor() {
  const list = document.getElementById('sec-editor-list');
  list.innerHTML = _reviewOutlineSections.map((s,i) => `
    <div class="sec-editor-item" draggable="true"
         ondragstart="onDragStart(event,${i})"
         ondragover="onDragOver(event,${i})"
         ondrop="onDrop(event,${i})"
         ondragleave="onDragLeave(event)"
         id="sec-item-${i}">
      <div class="sec-editor-row">
        <span class="sec-drag-handle">⠿</span>
        <input class="sec-editor-title" value="${esc(s.title)}"
               oninput="_reviewOutlineSections[${i}].title=this.value"
               placeholder="Название секции">
        <input class="sec-editor-words" type="number" value="${s.target_word_count}"
               min="50" max="3000" step="50"
               oninput="_reviewOutlineSections[${i}].target_word_count=parseInt(this.value)||200">
        <span style="font-size:10px;color:#45475a;flex-shrink:0">слов</span>
        <button class="sec-del-btn" onclick="deleteSection(${i})">×</button>
      </div>
    </div>`).join('');
  updateSecTotal();
}

function updateSecTotal() {
  const total = _reviewOutlineSections.reduce((s,x)=>s+(x.target_word_count||0),0);
  document.getElementById('sec-total').textContent =
    `Итого: ~${total} слов · ${_reviewOutlineSections.length} секций`;
}

function addSection() {
  _reviewOutlineSections.push({
    section_id: 'new_'+Date.now(),
    title: 'Новая секция',
    level: 'H2',
    target_word_count: 300,
    purpose: '',
    keywords: [],
    must_cover: [],
  });
  renderSecEditor();
  // Скроллим к новой секции
  const list = document.getElementById('sec-editor-list');
  list.lastElementChild && list.lastElementChild.scrollIntoView({behavior:'smooth'});
}

function deleteSection(i) {
  if (_reviewOutlineSections.length <= 1) return;
  _reviewOutlineSections.splice(i, 1);
  renderSecEditor();
}

// Drag & drop для секций
function onDragStart(e, i) {
  _dragSrcIdx = i;
  e.dataTransfer.effectAllowed = 'move';
  document.getElementById('sec-item-'+i).classList.add('dragging');
}
function onDragOver(e, i) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  document.querySelectorAll('.sec-editor-item').forEach(el=>{
    el.classList.remove('drag-over-top','drag-over-bot');
  });
  if (i !== _dragSrcIdx) {
    const el = document.getElementById('sec-item-'+i);
    const rect = el.getBoundingClientRect();
    if (e.clientY < rect.top + rect.height/2) el.classList.add('drag-over-top');
    else el.classList.add('drag-over-bot');
  }
}
function onDrop(e, i) {
  e.preventDefault();
  if (_dragSrcIdx === null || _dragSrcIdx === i) return;
  const el = document.getElementById('sec-item-'+i);
  const rect = el.getBoundingClientRect();
  const insertAfter = e.clientY >= rect.top + rect.height/2;
  const item = _reviewOutlineSections.splice(_dragSrcIdx, 1)[0];
  let targetIdx = i > _dragSrcIdx ? i-1 : i;
  if (insertAfter) targetIdx++;
  _reviewOutlineSections.splice(targetIdx, 0, item);
  _dragSrcIdx = null;
  renderSecEditor();
}
function onDragLeave(e) {
  document.querySelectorAll('.sec-editor-item').forEach(el=>{
    el.classList.remove('drag-over-top','drag-over-bot','dragging');
  });
}

function confirmReview() {
  if (!bridge) return;
  // Читаем актуальные значения из инпутов
  document.querySelectorAll('.sec-editor-title').forEach((inp,i)=>{
    if (_reviewOutlineSections[i]) _reviewOutlineSections[i].title = inp.value;
  });
  document.querySelectorAll('.sec-editor-words').forEach((inp,i)=>{
    if (_reviewOutlineSections[i])
      _reviewOutlineSections[i].target_word_count = parseInt(inp.value)||200;
  });

  // Вставляем выбранные gaps в нужные позиции
  _selectedGapIdx.forEach(i => {
    const g = _reviewGaps[i];
    if (!g) return;
    const title       = typeof g === 'string' ? g : (g.title || 'Новая секция');
    const after       = typeof g === 'string' ? '' : (g.after_section || '');
    const wordCount   = typeof g === 'string' ? 200 : (g.word_count || 200);
    const description = typeof g === 'string' ? '' : (g.description || '');

    const newSec = {
      section_id:        'gap_'+Date.now()+'_'+i,
      title,
      level:             'H2',
      target_word_count: wordCount,
      purpose:           description,
      keywords:          [],
      must_cover:        [],
    };

    // Ищем позицию для вставки
    if (after && after !== 'в конец') {
      const idx = _reviewOutlineSections.findIndex(s =>
        s.title.toLowerCase().includes(after.toLowerCase()) ||
        after.toLowerCase().includes(s.title.toLowerCase())
      );
      if (idx >= 0) {
        _reviewOutlineSections.splice(idx + 1, 0, newSec);
        return;
      }
    }
    // Если позиция не найдена или "в конец" — добавляем перед последней секцией
    // (обычно это "Заключение" или "Источники")
    const lastIdx = _reviewOutlineSections.length - 1;
    _reviewOutlineSections.splice(Math.max(0, lastIdx), 0, newSec);
  });

  const outlineData = {
    h1: document.getElementById('outline-h1').value,
    sections: _reviewOutlineSections,
    chosen_archetype_id: _reviewChosenArchetypeId,
  };
  bridge.resumePipeline(JSON.stringify(outlineData));
}

function toggleGap(i) {
  const cb   = document.getElementById('gap-cb-'+i);
  const item = document.getElementById('gap-item-'+i);
  if (_selectedGapIdx.has(i)) {
    _selectedGapIdx.delete(i);
    cb.checked = false;
    item.classList.remove('selected');
  } else {
    _selectedGapIdx.add(i);
    cb.checked = true;
    item.classList.add('selected');
  }
}

function cancelReview() {
  if (bridge) bridge.stopPipeline();
  hideReviewPanel();
}
function initSerpDragDrop() {
  const zone = document.getElementById('serp-zone');
  if (!zone) return;
  zone.addEventListener('dragover', e => {
    if (serpLoaded_) return;
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', e => {
    zone.classList.remove('drag-over');
  });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (serpLoaded_) return;
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!file.name.endsWith('.json')) {
      alert('Нужен файл в формате .json');
      return;
    }
    // Читаем файл в JS и передаём путь через bridge
    // QWebEngine не даёт реальный путь через drag-drop — читаем содержимое
    const reader = new FileReader();
    reader.onload = ev => {
      try {
        const content = ev.target.result;
        JSON.parse(content); // валидация
        if (bridge) bridge.loadSerpFromContent(file.name, content);
      } catch(e) {
        alert('Ошибка: файл не является валидным JSON');
      }
    };
    reader.readAsText(file);
  });
}

function frow(k,v){
  if(!v) return '';
  return `<div class="f-row"><div class="f-key">${esc(k)}</div><div class="f-val">${esc(String(v))}</div></div>`;
}

// Инициализация после загрузки
initSerpDragDrop();
goToStep('home');
__SITES_JS_PLACEHOLDER__
__ANALYTICS_JS_PLACEHOLDER__
</script>
</body>
</html>
"""
    return (html
            .replace("__SITES_JS_PLACEHOLDER__", _sites_js)
            .replace("__ANALYTICS_JS_PLACEHOLDER__", _analytics_js))
