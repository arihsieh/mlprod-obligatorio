import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger

from playwright.sync_api import Page

from mindful_news.browser import with_page
from mindful_news.config import load_config
from mindful_news.dates import parse_elpais_date
from mindful_news.enrich import enrich_headlines
from mindful_news.http import delay, fetch_article_meta, normalize_url, session
from mindful_news.models import Headline

MEDIO = "El País"
# /ultimas-noticias returns 403 from datacenter IPs — use section pages instead.
LATEST_SECTIONS = [
    "https://www.elpais.com.uy/informacion/politica",
    "https://www.elpais.com.uy/informacion/sociedad",
    "https://www.elpais.com.uy/informacion/policiales",
    "https://www.elpais.com.uy/informacion/judiciales",
    "https://www.elpais.com.uy/negocios/negocios",
    "https://www.elpais.com.uy/ovacion/futbol",
    "https://www.elpais.com.uy/tvshow/musica",
    "https://www.elpais.com.uy/mundo/estados-unidos",
]
SECTIONS = LATEST_SECTIONS + [
    "https://www.elpais.com.uy/informacion/salud",
    "https://www.elpais.com.uy/informacion/educacion",
    "https://www.elpais.com.uy/negocios/finanzas",
    "https://www.elpais.com.uy/ovacion/seleccion",
    "https://www.elpais.com.uy/tvshow/cine",
    "https://www.elpais.com.uy/vida-actual/ciencia",
    "https://www.elpais.com.uy/vida-actual/tecnologia",
    "https://www.elpais.com.uy/mundo/argentina",
]

ARTICLE_JS = """
() => {
    const seen = new Set();
    const skip = ['ultimas-noticias', 'suscripcion', 'RegPoliticas', '/tag/', '/autor/', '/buscar'];
    const results = [];
    for (const anchor of document.querySelectorAll('a[href*="elpais.com.uy"]')) {
        const url = anchor.href.split('?')[0];
        if (seen.has(url) || skip.some((part) => url.includes(part))) continue;
        const parts = url.replace('https://www.elpais.com.uy/', '').split('/').filter(Boolean);
        if (parts.length < 3) continue;
        const slug = parts[parts.length - 1];
        if (slug.length < 20) continue;
        const block = anchor.closest('article, li, [class*="Promo"], .PromoFlex, div');
        let title = '';
        if (block) {
            const heading = block.querySelector('h2, h3, .Promo-title, [class*="Title"]');
            if (heading) title = heading.textContent.trim();
        }
        if (title.length < 20) title = anchor.textContent.trim();
        if (title.length < 20) continue;
        seen.add(url);
        const imageNode = block ? block.querySelector('img') : null;
        const dateNode = block ? block.querySelector('.PromoBn-date, time, [class*="date"]') : null;
        results.push({
            external_id: url,
            titulo: title,
            url,
            thumbnail_url: imageNode ? (imageNode.currentSrc || imageNode.src) : null,
            seccion: parts[0] || null,
            fecha_raw: dateNode
                ? (dateNode.getAttribute('datetime') || dateNode.textContent.trim())
                : null,
        });
    }
    return results;
}
"""


def _raw_to_headlines(raw: list[dict]) -> list[Headline]:
    return [
        Headline(
            external_id=item["external_id"],
            titulo=item["titulo"],
            url=normalize_url(item["url"]),
            thumbnail_url=item.get("thumbnail_url"),
            medio=MEDIO,
            seccion=item.get("seccion"),
            fecha=parse_elpais_date(item.get("fecha_raw")),
        )
        for item in raw
    ]


def _dedupe(items: list[Headline]) -> list[Headline]:
    return list({h.url: h for h in items}.values())


def _scrape_sections(page: Page, sections: list[str], logger: Logger) -> list[Headline]:
    collected: list[Headline] = []
    for section_url in sections:
        page.goto(section_url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1)
        batch = _raw_to_headlines(page.evaluate(ARTICLE_JS))
        before = len(_dedupe(collected))
        collected.extend(batch)
        after = len(_dedupe(collected))
        logger.info("El País %s: batch=%d total=%d", section_url.split("/")[-1], len(batch), after)
        if after == before:
            logger.warning("El País %s returned no new articles", section_url)
    return collected


def _enrich_from_pages(headlines: list[Headline], logger: Logger) -> list[Headline]:
    cfg = load_config()
    by_url = {h.url: h for h in headlines}
    missing = [h for h in headlines if not h.fecha or not h.thumbnail_url]
    if not missing:
        return headlines

    def fetch(url: str) -> tuple[str, dict | None]:
        return url, fetch_article_meta(url, session())

    enriched = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, h.url) for h in missing]
        for index, future in enumerate(as_completed(futures), start=1):
            url, meta = future.result()
            if not meta:
                continue
            headline = by_url[url]
            if meta.get("fecha"):
                headline.fecha = meta["fecha"]
            thumb = meta.get("thumbnail_url")
            if thumb:
                headline.thumbnail_url = thumb
            enriched += 1
            if index % 100 == 0:
                delay(cfg["request_delay_min"] * 0.2, cfg["request_delay_max"] * 0.2)
    logger.info("El País enriched %d/%d from article pages", enriched, len(missing))
    return list(by_url.values())


def scrape_bulk(logger: Logger, target: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        return _scrape_sections(page, SECTIONS, logger)

    headlines = _dedupe(with_page(run))
    headlines = _enrich_from_pages(headlines, logger)
    headlines = enrich_headlines(headlines, logger)
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    logger.info("El País bulk: %d headlines", len(headlines))
    return headlines[:target]


def scrape_latest(logger: Logger, limit: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        return _scrape_sections(page, LATEST_SECTIONS, logger)

    headlines = _dedupe(with_page(run))
    headlines = _enrich_from_pages(headlines, logger)
    headlines = enrich_headlines(headlines, logger)
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    logger.info("El País latest: %d", min(len(headlines), limit))
    return headlines[:limit]
