from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from mindful_news.config import load_config
from mindful_news.db import fetch_needing_enrichment, update_metadata
from mindful_news.http import (
    delay,
    fetch_article_meta,
    fetch_eo_article,
    fetch_la_diaria_article,
    fetch_mvd_article,
    session,
)
from mindful_news.models import Headline

from mindful_news.thumbnails import clean_thumbnail


def fetch_meta_for_row(row: dict, sess=None) -> dict | None:
    own = sess or session()
    medio = row.get("medio") or ""
    url = row["url"]
    external_id = str(row.get("external_id") or "")

    if medio == "El Observador" and external_id.isdigit():
        meta = fetch_eo_article(int(external_id), own)
    elif medio == "Montevideo Portal" and external_id.isdigit():
        meta = fetch_mvd_article(int(external_id), own)
    elif medio == "La Diaria":
        meta = fetch_la_diaria_article(url, own)
    else:
        meta = fetch_article_meta(url, own)

    if not meta:
        return None
    meta["thumbnail_url"] = clean_thumbnail(meta.get("thumbnail_url"))
    return meta


def enrich_headlines(headlines: list[Headline], logger: logging.Logger | None = None) -> list[Headline]:
    """Fill missing thumbnail/fecha on in-memory headlines via article pages."""
    cfg = load_config()
    sess = session()
    missing = [h for h in headlines if not h.thumbnail_url or not h.fecha]
    if not missing:
        return headlines

    def work(headline: Headline) -> Headline:
        row = {
            "url": headline.url,
            "medio": headline.medio,
            "external_id": headline.external_id,
        }
        meta = fetch_meta_for_row(row, sess)
        if not meta:
            return headline
        if not headline.thumbnail_url and meta.get("thumbnail_url"):
            headline.thumbnail_url = meta["thumbnail_url"]
        if not headline.fecha and meta.get("fecha"):
            headline.fecha = meta["fecha"]
        if meta.get("titulo") and headline.medio == "La Diaria":
            headline.titulo = meta["titulo"]
        return headline

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(work, h) for h in missing]
        for index, future in enumerate(as_completed(futures), start=1):
            future.result()
            if index % 25 == 0:
                delay(cfg["request_delay_min"] * 0.15, cfg["request_delay_max"] * 0.15)

    if logger:
        with_thumb = sum(1 for h in headlines if h.thumbnail_url)
        logger.info("Enriched scrape batch: %d/%d with thumbnail", with_thumb, len(headlines))
    return headlines


def enrich_pending_from_db(
    logger: logging.Logger,
    *,
    limit: int | None = None,
) -> int:
    """Backfill thumbnail_url and fecha for all DB rows still missing them."""
    cfg = load_config()
    pending = fetch_needing_enrichment(limit=limit)
    if not pending:
        logger.info("No headlines need metadata enrichment")
        return 0

    logger.info("Enriching metadata for %d headlines", len(pending))
    sess = session()
    updated = 0
    batch: list[dict] = []

    def enrich(row: dict) -> dict | None:
        meta = fetch_meta_for_row(row, sess)
        if not meta:
            return None
        if not meta.get("fecha") and not meta.get("thumbnail_url"):
            return None
        return {"id": row["id"], "fecha": meta.get("fecha"), "thumbnail_url": meta.get("thumbnail_url")}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(enrich, row): row for row in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if result:
                batch.append(result)
            if index % 50 == 0:
                delay(cfg["request_delay_min"] * 0.2, cfg["request_delay_max"] * 0.2)
            if len(batch) >= 100:
                updated += update_metadata(batch)
                logger.info("Metadata enriched %d / %d", updated, index)
                batch.clear()

    if batch:
        updated += update_metadata(batch)
    logger.info("Metadata enrichment complete: %d rows updated", updated)
    return updated
