from __future__ import annotations

import logging

from mindful_news.config import load_config
from mindful_news.db import fetch_urls_for_medio, max_numeric_external_id
from mindful_news.enrich import enrich_headlines
from mindful_news.http import delay, fetch_eo_article, normalize_url, session
from mindful_news.models import Headline

MEDIO_EO = "El Observador"
MEDIO_MVD = "Montevideo Portal"


def _dedupe(headlines: list[Headline]) -> list[Headline]:
    by_key: dict[str, Headline] = {}
    for h in headlines:
        key = f"{h.medio}:{h.external_id or h.url}"
        by_key[key] = h
    return list(by_key.values())


def gap_fill_el_observador(logger: logging.Logger, max_misses: int = 120) -> list[Headline]:
    cfg = load_config()
    start_id = (max_numeric_external_id(MEDIO_EO) or 6_046_000) + 1
    headlines: list[Headline] = []
    misses = 0
    current = start_id
    sess = session()

    logger.info("EO gap fill from article id %d", start_id)
    while misses < max_misses:
        data = fetch_eo_article(current, sess)
        current += 1
        if not data:
            misses += 1
            if current % 20 == 0:
                delay(cfg["request_delay_min"] * 0.1, cfg["request_delay_max"] * 0.1)
            continue
        misses = 0
        headlines.append(
            Headline(
                external_id=data["external_id"],
                titulo=data["titulo"],
                url=data["url"],
                thumbnail_url=data.get("thumbnail_url"),
                medio=MEDIO_EO,
                seccion=data.get("seccion"),
                fecha=data.get("fecha"),
            )
        )
        if len(headlines) % 25 == 0:
            logger.info("EO gap fill: %d new articles (at id %d)", len(headlines), current)

    logger.info("EO gap fill done: %d articles", len(headlines))
    return enrich_headlines(headlines, logger)


def gap_fill_montevideo_portal(logger: logging.Logger, max_misses: int = 120) -> list[Headline]:
    from mindful_news.http import fetch_mvd_article

    cfg = load_config()
    start_id = (max_numeric_external_id(MEDIO_MVD) or 964_000) + 1
    headlines: list[Headline] = []
    misses = 0
    current = start_id
    sess = session()

    logger.info("MVD gap fill from article id %d", start_id)
    while misses < max_misses:
        data = fetch_mvd_article(current, sess)
        current += 1
        if not data:
            misses += 1
            if current % 20 == 0:
                delay(cfg["request_delay_min"] * 0.1, cfg["request_delay_max"] * 0.1)
            continue
        misses = 0
        headlines.append(
            Headline(
                external_id=data["external_id"],
                titulo=data["titulo"],
                url=data["url"],
                thumbnail_url=data.get("thumbnail_url"),
                medio=MEDIO_MVD,
                seccion=data.get("seccion") or "Noticias",
                fecha=data.get("fecha"),
            )
        )

    logger.info("MVD gap fill done: %d articles", len(headlines))
    return enrich_headlines(headlines, logger)


def gap_fill_la_diaria(logger: logging.Logger, limit: int = 200) -> list[Headline]:
    """Use sitemap-news for articles missing from DB; attach listing thumbnails."""
    from mindful_news.scrape.la_diaria import _attach_listing_thumbnails, _headlines_from_sitemap

    known = fetch_urls_for_medio("La Diaria")
    candidates = _headlines_from_sitemap(limit=limit * 3)
    headlines = [h for h in candidates if normalize_url(h.url) not in known]
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    headlines = headlines[:limit]
    headlines = _attach_listing_thumbnails(headlines, logger, hourly=True)
    logger.info("La Diaria gap fill: %d new articles from sitemap", len(headlines))
    return enrich_headlines(headlines, logger)


def gap_fill_el_pais(logger: logging.Logger, limit: int = 100) -> list[Headline]:
    from mindful_news.scrape.el_pais import scrape_latest

    known = fetch_urls_for_medio("El País")
    headlines = [h for h in scrape_latest(logger, limit=limit * 2) if h.url not in known]
    logger.info("El País gap fill: %d candidate articles", len(headlines))
    return headlines[:limit]


def gap_fill_all_sources(logger: logging.Logger, la_diaria_limit: int = 200) -> list[Headline]:
    collected: list[Headline] = []
    collected.extend(gap_fill_el_observador(logger))
    collected.extend(gap_fill_montevideo_portal(logger))
    collected.extend(gap_fill_la_diaria(logger, limit=la_diaria_limit))
    collected.extend(gap_fill_el_pais(logger))
    return _dedupe(collected)
