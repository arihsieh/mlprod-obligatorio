from __future__ import annotations

import logging
from typing import Callable

from mindful_news.config import load_config
from mindful_news.db import fetch_unclassified, init_db, save_headlines, update_classifications
from mindful_news.log import get_logger
from mindful_news.portal.api_client import predict_batch
from mindful_news.scrape import ALL_SOURCES, LATEST_SCRAPERS


def scrape_latest(logger: logging.Logger, limit: int | None = None) -> int:
    cfg = load_config()
    per_source = limit or int(cfg["hourly_limit_per_source"])
    total = 0
    for key in ALL_SOURCES:
        headlines = LATEST_SCRAPERS[key](logger, per_source)
        new = save_headlines(headlines, source_run="hourly")
        total += new
        logger.info("%s: %d fetched, %d new", key, len(headlines), new)
    return total


def classify_unclassified(
    logger: logging.Logger,
    *,
    limit: int | None = 200,
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


def run_hourly_pipeline(
    logger: logging.Logger | None = None,
    *,
    scrape_limit: int | None = None,
    classify_limit: int | None = 200,
) -> dict[str, int]:
    cfg = load_config()
    logger = logger or get_logger("portal.poller", int(cfg["log_level"]))
    init_db()

    scraped = scrape_latest(logger, limit=scrape_limit)
    classified = classify_unclassified(logger, limit=classify_limit)
    return {"scraped": scraped, "classified": classified}
