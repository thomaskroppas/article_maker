"""
CRUD-операции по таблицам PostgreSQL.
Все SQL-запросы только здесь — агенты и оркестратор не знают про БД.
Когда будет FastAPI — роутеры будут вызывать эти же функции напрямую.
"""
from typing import Optional, List
from app.storage.db_manager import get_connection, release_connection
from app.utils.time_utils import now_iso


class _DB:
    """Автоматически берёт и возвращает соединение из пула."""
    def __enter__(self):
        self.conn = get_connection()
        self.cur  = self.conn.cursor()
        return self.cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.cur.close()
        release_connection(self.conn)
        return False


# ─── Sites ────────────────────────────────────────────────────────────────────

def create_site(domain: str, name: str, niche_id: Optional[str] = None,
                is_test: bool = False) -> None:
    """Создаёт сайт. Если домен уже есть — ничего не делает (idempotent)."""
    with _DB() as cur:
        cur.execute("""
            INSERT INTO sites (domain, name, niche_id, is_test, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (domain) DO NOTHING
        """, (domain, name, niche_id, is_test, now_iso()))


def get_all_sites(include_test: bool = True) -> List[dict]:
    """Возвращает все сайты. Если include_test=False — без тестовых."""
    with _DB() as cur:
        if include_test:
            cur.execute("SELECT * FROM sites ORDER BY created_at DESC")
        else:
            cur.execute("SELECT * FROM sites WHERE is_test=FALSE ORDER BY created_at DESC")
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_site(domain: str) -> Optional[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM sites WHERE domain=%s", (domain,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


def count_articles_for_site(domain: str) -> int:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) FROM articles WHERE site_domain=%s", (domain,))
        return cur.fetchone()[0]


# ─── Authors ──────────────────────────────────────────────────────────────────

def create_author(author_id: str, site_domain: str, name: str,
                  character: Optional[str] = None,
                  tone: Optional[str] = None,
                  age_image: Optional[str] = None,
                  niche_id: Optional[str] = None,
                  reference_id: Optional[str] = None,
                  is_active: bool = True) -> None:
    """Создаёт автора для сайта. Если author_id уже есть — ничего не делает."""
    with _DB() as cur:
        cur.execute("""
            INSERT INTO authors (author_id, site_domain, name, character,
                                 tone, age_image, niche_id, reference_id,
                                 is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (author_id) DO NOTHING
        """, (author_id, site_domain, name, character, tone,
              age_image, niche_id, reference_id, is_active, now_iso()))


def get_authors_for_site(site_domain: str, only_active: bool = True) -> List[dict]:
    """Возвращает пул авторов сайта. Используется для случайного выбора."""
    with _DB() as cur:
        if only_active:
            cur.execute(
                "SELECT * FROM authors WHERE site_domain=%s AND is_active=TRUE "
                "ORDER BY created_at",
                (site_domain,)
            )
        else:
            cur.execute(
                "SELECT * FROM authors WHERE site_domain=%s ORDER BY created_at",
                (site_domain,)
            )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_author(author_id: str) -> Optional[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM authors WHERE author_id=%s", (author_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


def count_authors_for_site(domain: str, only_active: bool = False) -> int:
    with _DB() as cur:
        if only_active:
            cur.execute(
                "SELECT COUNT(*) FROM authors WHERE site_domain=%s AND is_active=TRUE",
                (domain,)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM authors WHERE site_domain=%s",
                (domain,)
            )
        return cur.fetchone()[0]


def set_author_active(author_id: str, is_active: bool) -> None:
    with _DB() as cur:
        cur.execute(
            "UPDATE authors SET is_active=%s WHERE author_id=%s",
            (is_active, author_id)
        )


def get_authors_in_niche(niche_id: str, exclude_site: Optional[str] = None) -> List[dict]:
    """
    Возвращает авторов из указанной ниши, опционально исключая один сайт.
    Используется для будущей механики «копировать как образец» при создании
    нового сайта в той же нише.
    """
    with _DB() as cur:
        if exclude_site:
            cur.execute(
                "SELECT * FROM authors WHERE niche_id=%s AND site_domain<>%s "
                "ORDER BY created_at DESC",
                (niche_id, exclude_site)
            )
        else:
            cur.execute(
                "SELECT * FROM authors WHERE niche_id=%s ORDER BY created_at DESC",
                (niche_id,)
            )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ─── Niches ───────────────────────────────────────────────────────────────────

def get_all_niches() -> List[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM niches ORDER BY niche_id")
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_niche(niche_id: str) -> Optional[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM niches WHERE niche_id=%s", (niche_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


# ─── Archetypes ───────────────────────────────────────────────────────────────

def get_archetypes_for_niche(niche_id: str) -> List[dict]:
    """Все архетипы ниши. Используется при автоподборе и в UI."""
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM archetypes WHERE niche_id=%s ORDER BY archetype_id",
            (niche_id,)
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_archetype(archetype_id: str) -> Optional[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM archetypes WHERE archetype_id=%s", (archetype_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


# ─── Archetype picks (лог автоподбора) ────────────────────────────────────────

def log_archetype_pick(article_id: str,
                       suggested_archetype_id: Optional[str],
                       chosen_archetype_id: str,
                       niche_id: Optional[str],
                       intent: Optional[str]) -> None:
    """
    Записывает решение по выбору архетипа: что система предложила и что
    юзер выбрал. matched вычисляется автоматически. Если suggested=None
    (автоподбор не сработал) — matched=False.
    """
    matched = (suggested_archetype_id is not None
               and suggested_archetype_id == chosen_archetype_id)
    with _DB() as cur:
        cur.execute("""
            INSERT INTO archetype_picks (article_id, suggested_archetype_id,
                                         chosen_archetype_id, matched,
                                         niche_id, intent, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (article_id, suggested_archetype_id, chosen_archetype_id,
              matched, niche_id, intent, now_iso()))


def get_archetype_pick_stats(niche_id: Optional[str] = None) -> dict:
    """
    Статистика точности автоподбора: всего записей, совпало, доля.
    Можно фильтровать по нише.
    """
    with _DB() as cur:
        if niche_id:
            cur.execute("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE matched) AS matched_count
                FROM archetype_picks
                WHERE niche_id=%s AND suggested_archetype_id IS NOT NULL
            """, (niche_id,))
        else:
            cur.execute("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE matched) AS matched_count
                FROM archetype_picks
                WHERE suggested_archetype_id IS NOT NULL
            """)
        row = cur.fetchone()
        total, matched_count = row[0], row[1]
        accuracy = (matched_count / total) if total > 0 else None
        return {
            "total": total,
            "matched": matched_count,
            "accuracy": accuracy,  # None если статистики нет
        }


def get_recent_archetype_picks(limit: int = 20) -> List[dict]:
    """Последние N решений по выбору архетипа (для просмотра/отладки)."""
    with _DB() as cur:
        cur.execute("""
            SELECT * FROM archetype_picks
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ─── Articles ─────────────────────────────────────────────────────────────────

def upsert_article(article_id: str, site_domain: str,
                   author_id: Optional[str],
                   title: str, main_keyword: str,
                   status: str, created_at: str) -> None:
    with _DB() as cur:
        cur.execute("""
            INSERT INTO articles (article_id, site_domain, author_id, title, main_keyword, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (article_id) DO UPDATE SET
                site_domain  = EXCLUDED.site_domain,
                author_id    = EXCLUDED.author_id,
                title        = EXCLUDED.title,
                main_keyword = EXCLUDED.main_keyword,
                status       = EXCLUDED.status,
                updated_at   = EXCLUDED.updated_at
        """, (article_id, site_domain, author_id, title, main_keyword, status, created_at, now_iso()))


def update_article_status(article_id: str, status: str) -> None:
    with _DB() as cur:
        cur.execute(
            "UPDATE articles SET status=%s, updated_at=%s WHERE article_id=%s",
            (status, now_iso(), article_id)
        )


def update_article_qa(article_id: str, qa_status: str, qa_score: int) -> None:
    with _DB() as cur:
        cur.execute(
            "UPDATE articles SET qa_status=%s, qa_score=%s, updated_at=%s WHERE article_id=%s",
            (qa_status, qa_score, now_iso(), article_id)
        )


def get_all_articles() -> List[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM articles ORDER BY created_at DESC")
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_article(article_id: str) -> Optional[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM articles WHERE article_id=%s", (article_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


# ─── Pipeline steps ───────────────────────────────────────────────────────────

def log_step_start(article_id: str, step_name: str) -> int:
    with _DB() as cur:
        cur.execute("""
            INSERT INTO pipeline_steps (article_id, step_name, status, started_at)
            VALUES (%s, %s, 'running', %s)
            RETURNING id
        """, (article_id, step_name, now_iso()))
        return cur.fetchone()[0]


def log_step_finish(row_id: int, status: str = "done",
                    error_message: str = "") -> None:
    with _DB() as cur:
        cur.execute("""
            UPDATE pipeline_steps
            SET status=%s, finished_at=%s, error_message=%s
            WHERE id=%s
        """, (status, now_iso(), error_message, row_id))


def get_steps_for_article(article_id: str) -> List[dict]:
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM pipeline_steps WHERE article_id=%s ORDER BY id",
            (article_id,)
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ─── Sections ─────────────────────────────────────────────────────────────────

def upsert_section(article_id: str, section_id: str,
                   status: str, iterations: int, word_count: int) -> None:
    with _DB() as cur:
        cur.execute("""
            INSERT INTO sections (article_id, section_id, status, iterations, word_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (article_id, section_id, status, iterations, word_count))
        cur.execute("""
            UPDATE sections SET status=%s, iterations=%s, word_count=%s
            WHERE article_id=%s AND section_id=%s
        """, (status, iterations, word_count, article_id, section_id))

# ─── Style references (писатели-референсы) ────────────────────────────────────

def get_all_style_references(language: Optional[str] = None,
                             geo: Optional[str] = None,
                             niche: Optional[str] = None,
                             only_active: bool = True) -> List[dict]:
    """
    Возвращает каталог писателей-референсов с опциональными фильтрами.
    niche фильтрует по niche_tags (массиву); если ниши там нет — пропускаем.
    """
    where = []
    args = []
    if only_active:
        where.append("is_active=TRUE")
    if language:
        where.append("language=%s")
        args.append(language)
    if geo:
        where.append("geo=%s")
        args.append(geo)
    if niche:
        where.append("(%s = ANY(niche_tags) OR array_length(niche_tags,1) IS NULL)")
        args.append(niche)
    sql = "SELECT * FROM style_references"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name"
    with _DB() as cur:
        cur.execute(sql, args)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_style_reference(reference_id: str) -> Optional[dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM style_references WHERE reference_id=%s",
                    (reference_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


def create_style_reference(reference_id: str, name: str, language: str, geo: str,
                           niche_tags: Optional[List[str]] = None,
                           notes: Optional[str] = None,
                           is_active: bool = True) -> None:
    with _DB() as cur:
        cur.execute("""
            INSERT INTO style_references
                (reference_id, name, language, geo, niche_tags, notes, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (reference_id) DO NOTHING
        """, (reference_id, name, language, geo, niche_tags or [],
              notes, is_active, now_iso()))
        
def save_extracted_style(reference_id: str,
                         character: str,
                         tone: str = "",
                         age_image: str = "") -> None:
    """Сохраняет извлечённые поля стиля в кэш (поля в style_references)."""
    with _DB() as cur:
        cur.execute("""
            UPDATE style_references
               SET extracted_style=%s,
                   extracted_tone=%s,
                   extracted_age_image=%s
             WHERE reference_id=%s
        """, (character, tone, age_image, reference_id))

def update_article_cost(article_id: str, cost_usd: float) -> None:
    """Обновляет накопленную стоимость статьи в БД."""
    with _DB() as cur:
        cur.execute(
            "UPDATE articles SET cost_usd=%s WHERE article_id=%s",
            (cost_usd, article_id),
        )