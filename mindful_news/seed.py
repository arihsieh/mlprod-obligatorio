from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from mindful_news.config import ROOT
from mindful_news.db import connection, init_db

SPLITS_DIR = ROOT / "data" / "splits"
SPLIT_FILES = ("train.csv", "val.csv", "test.csv")
TEST_URL_PATTERN = "%test.mindful-news.local%"
BATCH_SIZE = 500

SEED_HEADLINE = """
INSERT INTO headlines (
    external_id, titulo, url, thumbnail_url, medio, seccion, fecha,
    scraped_at, source_run, tema, carga, classified_at
) VALUES (
    %(external_id)s, %(titulo)s, %(url)s, %(thumbnail_url)s,
    %(medio)s, %(seccion)s, %(fecha)s, %(scraped_at)s, %(source_run)s,
    %(tema)s, %(carga)s, %(classified_at)s
)
ON DUPLICATE KEY UPDATE
    titulo = VALUES(titulo),
    thumbnail_url = COALESCE(VALUES(thumbnail_url), thumbnail_url),
    seccion = COALESCE(VALUES(seccion), seccion),
    fecha = COALESCE(VALUES(fecha), fecha),
    scraped_at = VALUES(scraped_at),
    source_run = VALUES(source_run),
    tema = COALESCE(VALUES(tema), tema),
    carga = COALESCE(VALUES(carga), carga),
    classified_at = COALESCE(VALUES(classified_at), classified_at)
"""


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_row(raw: dict[str, str]) -> dict | None:
    url = (raw.get("url") or "").strip()
    titulo = (raw.get("titulo") or "").strip()
    if not url or not titulo or "test.mindful-news.local" in url:
        return None
    return {
        "external_id": (raw.get("external_id") or url).strip()[:512],
        "titulo": titulo,
        "url": url[:512],
        "thumbnail_url": (raw.get("thumbnail_url") or "").strip() or None,
        "medio": (raw.get("medio") or "").strip()[:64],
        "seccion": ((raw.get("seccion") or "").strip()[:255] or None),
        "fecha": _parse_dt(raw.get("fecha")),
        "scraped_at": _parse_dt(raw.get("scraped_at")) or datetime.utcnow(),
        "source_run": (raw.get("source_run") or "dataset").strip()[:32],
        "tema": (raw.get("tema") or "").strip() or None,
        "carga": (raw.get("carga") or "").strip() or None,
        "classified_at": _parse_dt(raw.get("classified_at")),
    }


def load_split_rows(splits_dir: Path = SPLITS_DIR) -> list[dict]:
    by_url: dict[str, dict] = {}
    for name in SPLIT_FILES:
        path = splits_dir / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                row = _parse_row(raw)
                if row and row.get("tema") and row.get("carga") and row.get("classified_at"):
                    by_url[row["url"]] = row
    return list(by_url.values())


def count_real_headlines() -> int:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM headlines WHERE url NOT LIKE %s",
                (TEST_URL_PATTERN,),
            )
            return int(cursor.fetchone()["total"])


def purge_test_headlines() -> int:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM headlines WHERE url LIKE %s", (TEST_URL_PATTERN,))
            deleted = cursor.rowcount
        conn.commit()
    return deleted


def seed_from_splits(splits_dir: Path = SPLITS_DIR) -> int:
    rows = load_split_rows(splits_dir)
    if not rows:
        return 0

    inserted = 0
    with connection() as conn:
        try:
            with conn.cursor() as cursor:
                for start in range(0, len(rows), BATCH_SIZE):
                    batch = rows[start : start + BATCH_SIZE]
                    for row in batch:
                        cursor.execute(SEED_HEADLINE, row)
                        if cursor.rowcount == 1:
                            inserted += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return inserted


def seed_from_splits_if_needed(
    splits_dir: Path = SPLITS_DIR,
    logger: logging.Logger | None = None,
) -> int:
    """Load classified headlines from data/splits when DB has no real rows."""
    init_db()
    if count_real_headlines() > 0:
        return 0
    if not splits_dir.exists():
        return 0

    removed = purge_test_headlines()
    loaded = seed_from_splits(splits_dir)
    if logger and (loaded or removed):
        logger.info(
            "Seeded %d headlines from %s (removed %d test rows)",
            loaded,
            splits_dir,
            removed,
        )
    return loaded
