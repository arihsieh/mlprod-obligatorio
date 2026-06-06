from mindful_news.scrape.el_observador import scrape_bulk as eo_bulk, scrape_latest as eo_latest
from mindful_news.scrape.el_pais import scrape_bulk as ep_bulk, scrape_latest as ep_latest
from mindful_news.scrape.la_diaria import scrape_bulk as ld_bulk, scrape_latest as ld_latest
from mindful_news.scrape.montevideo_portal import scrape_bulk as mvd_bulk, scrape_latest as mvd_latest

BULK_SCRAPERS = {
    "montevideo_portal": mvd_bulk,
    "el_pais": ep_bulk,
    "la_diaria": ld_bulk,
    "el_observador": eo_bulk,
}

LATEST_SCRAPERS = {
    "montevideo_portal": mvd_latest,
    "el_pais": ep_latest,
    "la_diaria": ld_latest,
    "el_observador": eo_latest,
}

ALL_SOURCES = list(BULK_SCRAPERS.keys())
