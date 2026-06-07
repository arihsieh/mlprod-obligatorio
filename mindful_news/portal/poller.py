from __future__ import annotations

import logging
from typing import Callable

from mindful_news.config import load_config
from mindful_news.db import fetch_unclassified, init_db, save_headlines, update_classifications
from mindful_news.enrich import enrich_pending_from_db
from mindful_news.log import get_logger
from mindful_news.portal.api_client import predict_batch
from mindful_news.scrape import ALL_SOURCES, LATEST_SCRAPERS
from mindful_news.scrape.gap_fill import gap_fill_all_sources

_CLASSIFY_BATCH = 200


def scrape_latest(logger: logging.Logger, limit: int | None = None) -> int:
    cfg = load_config()
    per_source = limit or int(cfg["hourly_limit_per_source"])
    total = 0
    for key in ALL_SOURCES:
        headlines = LATEST_SCRAPERS[key](logger, per_source)
        new = save_headlines(headlines, source_run="hourly")
        total += new
        logger.info("%s listing: %d fetched, %d new", key, len(headlines), new)
    return total


def gap_fill_since_last(logger: logging.Logger, la_diaria_limit: int = 200) -> int:
    headlines = gap_fill_all_sources(logger, la_diaria_limit=la_diaria_limit)
    new = save_headlines(headlines, source_run="hourly")
    logger.info("Gap fill: %d fetched, %d new", len(headlines), new)
    return new


def classify_unclassified(
    logger: logging.Logger,
    *,
    limit: int | None = _CLASSIFY_BATCH,
    predict_fn: Callable[[list[dict]], list[dict]] | None = None,
) -> int:
    rows = fetch_unclassified(limit=limit)
    if not rows:
        logger.info("No hay titulares sin clasificar")
        return 0

    items = [{"titulo": row["titulo"], "seccion": row.get("seccion")} for row in rows]
    batch_predict = predict_fn or predict_batch
    results = batch_predict(items)
    if len(results) != len(rows):
        raise RuntimeError(f"API devolvió {len(results)} resultados para {len(rows)} titulares")

    updates = [
        {"id": row["id"], "tema": result["tema"], "carga": result["carga"]}
        for row, result in zip(rows, results)
    ]
    saved = update_classifications(updates)
    logger.info("Clasificados %d titulares vía API", saved)
    return saved


def classify_all_pending(
    logger: logging.Logger,
    *,
    predict_fn: Callable[[list[dict]], list[dict]] | None = None,
) -> int:
    total = 0
    while True:
        count = classify_unclassified(logger, limit=_CLASSIFY_BATCH, predict_fn=predict_fn)
        if count == 0:
            break
        total += count
    return total


def run_hourly_pipeline(
    logger: logging.Logger | None = None,
    *,
    scrape_limit: int | None = None,
    classify_limit: int | None = None,
) -> dict[str, int]:
    cfg = load_config()
    logger = logger or get_logger("portal.poller", int(cfg["log_level"]))
    init_db()

    gap_new = gap_fill_since_last(logger, la_diaria_limit=(scrape_limit or int(cfg["hourly_limit_per_source"])) * 4)
    scraped = scrape_latest(logger, limit=scrape_limit)
    enriched = enrich_pending_from_db(logger)

    if classify_limit is None:
        classified = classify_all_pending(logger)
    else:
        classified = classify_unclassified(logger, limit=classify_limit)

    return {
        "gap_new": gap_new,
        "scraped": scraped,
        "enriched": enriched,
        "classified": classified,
    }
