#!/usr/bin/env python3
"""Fetch article pages to backfill missing thumbnail_url and fecha."""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mindful_news.config import load_config
from mindful_news.db import connection, init_db, update_metadata
from mindful_news.http import delay, fetch_article_meta, session
from mindful_news.log import get_logger

MEDIO_LABELS = {
    "montevideo_portal": "Montevideo Portal",
    "el_pais": "El País",
    "la_diaria": "La Diaria",
    "el_observador": "El Observador",
}


def _needs_enrichment(medio: str | None) -> list[dict]:
    query = """
        SELECT id, url, medio
        FROM headlines
        WHERE (fecha IS NULL OR thumbnail_url IS NULL OR thumbnail_url = '')
    """
    params: tuple = ()
    if medio:
        query += " AND medio = %s"
        params = (medio,)
    query += " ORDER BY COALESCE(fecha, scraped_at) DESC, id ASC"
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill thumbnail and fecha from article pages.")
    parser.add_argument("--sources", nargs="*", default=list(MEDIO_LABELS.keys()))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config()
    logger = get_logger("enrich_metadata", int(cfg["log_level"]))
    init_db()

    sess = session()
    pending: list[dict] = []
    for key in args.sources:
        medio = MEDIO_LABELS.get(key)
        if not medio:
            raise SystemExit(f"Unknown source: {key}")
        pending.extend(_needs_enrichment(medio))
    if args.limit:
        pending = pending[: args.limit]

    logger.info("Enriching metadata for %d headlines", len(pending))
    if not pending:
        return

    def enrich(row: dict) -> dict | None:
        meta = fetch_article_meta(row["url"], sess)
        if not meta:
            return None
        thumb = meta.get("thumbnail_url")
        if thumb and ("mtg_image" in thumb or "lazy" in thumb):
            thumb = None
        if not meta.get("fecha") and not thumb:
            return None
        return {"id": row["id"], "fecha": meta.get("fecha"), "thumbnail_url": thumb}

    updated = 0
    batch: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(enrich, row): row for row in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if result:
                batch.append(result)
            if index % 50 == 0:
                delay(cfg["request_delay_min"] * 0.2, cfg["request_delay_max"] * 0.2)
            if len(batch) >= 100:
                updated += update_metadata(batch)
                logger.info("Updated %d / %d", updated, index)
                batch.clear()
    if batch:
        updated += update_metadata(batch)
    logger.info("Metadata enrichment complete: %d rows updated", updated)


if __name__ == "__main__":
    main()
