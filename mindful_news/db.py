from contextlib import contextmanager
from typing import Iterator

import pymysql
from pymysql.connections import Connection

from mindful_news.config import load_config
from mindful_news.dedup import stable_external_id
from mindful_news.models import Headline

CREATE_HEADLINES_TABLE = """
CREATE TABLE IF NOT EXISTS headlines (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id VARCHAR(512) NOT NULL,
    titulo TEXT NOT NULL,
    url VARCHAR(512) NOT NULL,
    thumbnail_url TEXT,
    medio VARCHAR(64) NOT NULL,
    seccion VARCHAR(255),
    fecha DATETIME NULL,
    scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_run VARCHAR(32) NOT NULL,
    tema VARCHAR(32) NULL,
    carga VARCHAR(16) NULL,
    classified_at DATETIME NULL,
    UNIQUE KEY uq_headlines_url (url),
    KEY idx_medio_fecha (medio, fecha),
    KEY idx_scraped_at (scraped_at),
    KEY idx_unclassified (classified_at, id)
)
"""

MIGRATIONS = [
    "ALTER TABLE headlines MODIFY COLUMN seccion VARCHAR(255) NULL",
    "ALTER TABLE headlines MODIFY COLUMN external_id VARCHAR(512) NOT NULL",
    "ALTER TABLE headlines ADD COLUMN tema VARCHAR(32) NULL",
    "ALTER TABLE headlines ADD COLUMN carga VARCHAR(16) NULL",
    "ALTER TABLE headlines ADD COLUMN classified_at DATETIME NULL",
    "CREATE INDEX idx_unclassified ON headlines (classified_at, id)",
]

INSERT_HEADLINE = """
INSERT INTO headlines (
    external_id, titulo, url, thumbnail_url, medio, seccion, fecha, source_run
) VALUES (
    %(external_id)s, %(titulo)s, %(url)s, %(thumbnail_url)s,
    %(medio)s, %(seccion)s, %(fecha)s, %(source_run)s
)
ON DUPLICATE KEY UPDATE
    url = VALUES(url),
    titulo = VALUES(titulo),
    thumbnail_url = COALESCE(VALUES(thumbnail_url), thumbnail_url),
    seccion = COALESCE(VALUES(seccion), seccion),
    fecha = COALESCE(VALUES(fecha), fecha),
    scraped_at = CURRENT_TIMESTAMP,
    source_run = VALUES(source_run)
"""


def _db_settings() -> dict:
    db = load_config()["database"]
    return {
        "host": db["host"],
        "port": int(db["port"]),
        "user": db["user"],
        "password": db["password"],
        "database": db["name"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


@contextmanager
def connection() -> Iterator[Connection]:
    conn = pymysql.connect(**_db_settings())
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_HEADLINES_TABLE)
            for statement in MIGRATIONS:
                try:
                    cursor.execute(statement)
                except pymysql.Error as exc:
                    if exc.args[0] not in (1060, 1061, 1062):
                        raise
        conn.commit()
    merge_duplicate_external_ids()
    with connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "CREATE UNIQUE INDEX uq_headlines_medio_external "
                    "ON headlines (medio, external_id(191))"
                )
            except pymysql.Error as exc:
                if exc.args[0] != 1061:
                    raise
        conn.commit()


def merge_duplicate_external_ids() -> int:
    """Drop duplicate rows that share medio + numeric external_id (keep newest)."""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT medio, external_id,
                       GROUP_CONCAT(id ORDER BY scraped_at DESC, id DESC) AS ids
                FROM headlines
                WHERE external_id REGEXP '^[0-9]+$'
                GROUP BY medio, external_id
                HAVING COUNT(*) > 1
                """
            )
            groups = list(cursor.fetchall())
            removed = 0
            for group in groups:
                ids = [int(value) for value in group["ids"].split(",")]
                drop_ids = ids[1:]
                if not drop_ids:
                    continue
                placeholders = ", ".join(["%s"] * len(drop_ids))
                cursor.execute(f"DELETE FROM headlines WHERE id IN ({placeholders})", drop_ids)
                removed += len(drop_ids)
        conn.commit()
    return removed


def save_headlines(headlines: list[Headline], source_run: str) -> int:
    """Insert headlines; dedupe by URL and (medio, external_id). Returns new row count."""
    if not headlines:
        return 0
    rows = [
        {
            "external_id": stable_external_id(h)[:512],
            "titulo": h.titulo,
            "url": h.url,
            "thumbnail_url": h.thumbnail_url,
            "medio": h.medio,
            "seccion": (h.seccion or "")[:255] or None,
            "fecha": h.fecha,
            "source_run": source_run,
        }
        for h in headlines
    ]
    inserted = 0
    with connection() as conn:
        try:
            with conn.cursor() as cursor:
                for row in rows:
                    cursor.execute(INSERT_HEADLINE, row)
                    if cursor.rowcount == 1:
                        inserted += 1
            conn.commit()
            return inserted
        except pymysql.Error:
            conn.rollback()
            raise


def fetch_unclassified(limit: int | None = None) -> list[dict]:
    query = (
        "SELECT id, titulo, url, medio, seccion FROM headlines "
        "WHERE classified_at IS NULL "
        "ORDER BY COALESCE(fecha, scraped_at) DESC, id ASC"
    )
    if limit is not None:
        query += " LIMIT %s"
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,) if limit is not None else ())
            return list(cursor.fetchall())


def fetch_needing_enrichment(limit: int | None = None) -> list[dict]:
    query = """
        SELECT id, url, medio, external_id
        FROM headlines
        WHERE thumbnail_url IS NULL OR thumbnail_url = '' OR fecha IS NULL
        ORDER BY scraped_at DESC, id ASC
    """
    if limit is not None:
        query += " LIMIT %s"
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,) if limit is not None else ())
            return list(cursor.fetchall())


def max_numeric_external_id(medio: str) -> int | None:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT MAX(CAST(external_id AS UNSIGNED)) AS max_id
                FROM headlines
                WHERE medio = %s AND external_id REGEXP '^[0-9]+$'
                """,
                (medio,),
            )
            row = cursor.fetchone()
            value = row["max_id"] if row else None
            return int(value) if value is not None else None


def fetch_urls_for_medio(medio: str) -> set[str]:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT url FROM headlines WHERE medio = %s", (medio,))
            return {row["url"] for row in cursor.fetchall()}


def count_unclassified() -> int:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM headlines WHERE classified_at IS NULL")
            return int(cursor.fetchone()["total"])


def update_classifications(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        UPDATE headlines
        SET tema = %(tema)s, carga = %(carga)s, classified_at = CURRENT_TIMESTAMP
        WHERE id = %(id)s
    """
    with connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()
            return len(rows)
        except pymysql.Error:
            conn.rollback()
            raise


def update_metadata(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        UPDATE headlines
        SET
            thumbnail_url = COALESCE(%(thumbnail_url)s, thumbnail_url),
            fecha = COALESCE(%(fecha)s, fecha)
        WHERE id = %(id)s
    """
    with connection() as conn:
        try:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()
            return len(rows)
        except pymysql.Error:
            conn.rollback()
            raise


def _headline_filter_clauses(
    temas: list[str] | None = None,
    cargas: list[str] | None = None,
    medios: list[str] | None = None,
) -> tuple[list[str], list[object]]:
    clauses = [
        "classified_at IS NOT NULL",
        "url NOT LIKE %s",
    ]
    params: list[object] = ["%test.mindful-news.local%"]
    if temas:
        placeholders = ", ".join(["%s"] * len(temas))
        clauses.append(f"tema IN ({placeholders})")
        params.extend(temas)
    if cargas:
        placeholders = ", ".join(["%s"] * len(cargas))
        clauses.append(f"carga IN ({placeholders})")
        params.extend(cargas)
    if medios:
        placeholders = ", ".join(["%s"] * len(medios))
        clauses.append(f"medio IN ({placeholders})")
        params.extend(medios)
    return clauses, params


def count_headlines(
    temas: list[str] | None = None,
    cargas: list[str] | None = None,
    medios: list[str] | None = None,
) -> int:
    clauses, params = _headline_filter_clauses(temas, cargas, medios)
    where = " AND ".join(clauses)
    query = f"SELECT COUNT(*) AS total FROM headlines WHERE {where}"
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return int(cursor.fetchone()["total"])


def fetch_headlines(
    temas: list[str] | None = None,
    cargas: list[str] | None = None,
    medios: list[str] | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    clauses, params = _headline_filter_clauses(temas, cargas, medios)
    where = " AND ".join(clauses)
    query = f"""
        SELECT id, titulo, url, thumbnail_url, medio, seccion, fecha, tema, carga, scraped_at
        FROM headlines
        WHERE {where}
        ORDER BY GREATEST(COALESCE(fecha, scraped_at), scraped_at) DESC, id DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())


def stats() -> dict:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT medio, COUNT(*) AS total FROM headlines GROUP BY medio ORDER BY medio")
            by_medio = list(cursor.fetchall())
            cursor.execute("SELECT COUNT(*) AS total FROM headlines WHERE classified_at IS NULL")
            unclassified = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT tema, carga, COUNT(*) AS total FROM headlines "
                "WHERE classified_at IS NOT NULL GROUP BY tema, carga ORDER BY tema, carga"
            )
            labels = list(cursor.fetchall())
    return {"by_medio": by_medio, "unclassified": unclassified, "labels": labels}
