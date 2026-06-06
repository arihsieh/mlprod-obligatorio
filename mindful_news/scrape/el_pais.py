import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger

from playwright.sync_api import Page

from mindful_news.browser import with_page
from mindful_news.config import load_config
from mindful_news.dates import parse_elpais_date
from mindful_news.http import delay, fetch_article_meta, normalize_url, session
from mindful_news.models import Headline

MEDIO = "El País"
LISTING_URL = "https://www.elpais.com.uy/ultimas-noticias"
SECTIONS = [
    "https://www.elpais.com.uy/informacion/politica",
    "https://www.elpais.com.uy/informacion/sociedad",
    "https://www.elpais.com.uy/informacion/policiales",
    "https://www.elpais.com.uy/informacion/salud",
    "https://www.elpais.com.uy/informacion/judiciales",
    "https://www.elpais.com.uy/informacion/educacion",
    "https://www.elpais.com.uy/negocios/negocios",
    "https://www.elpais.com.uy/negocios/finanzas",
    "https://www.elpais.com.uy/ovacion/futbol",
    "https://www.elpais.com.uy/ovacion/seleccion",
    "https://www.elpais.com.uy/tvshow/musica",
    "https://www.elpais.com.uy/tvshow/cine",
    "https://www.elpais.com.uy/vida-actual/ciencia",
    "https://www.elpais.com.uy/vida-actual/tecnologia",
    "https://www.elpais.com.uy/mundo/estados-unidos",
    "https://www.elpais.com.uy/mundo/argentina",
]

ULTIMAS_JS = """
() => [...document.querySelectorAll('.PromoBn')].map((promo) => {
    const titleNode = promo.querySelector('.Promo-title');
    const linkNode = promo.querySelector('a[href]');
    const dateNode = promo.querySelector('.PromoBn-date');
    const imageNode = promo.querySelector('img');
    if (!titleNode || !linkNode) return null;
    return {
        external_id: linkNode.href,
        titulo: titleNode.textContent.trim(),
        url: linkNode.href.split('?')[0],
        thumbnail_url: imageNode ? imageNode.src : null,
        seccion: promo.querySelector('.Promo-category')?.textContent?.trim() || null,
        fecha_raw: dateNode ? dateNode.textContent.trim() : null,
    };
}).filter(Boolean)
"""

SECTION_JS = """
() => {
    const seen = new Set();
    const results = [];
    for (const anchor of document.querySelectorAll('a[href*="elpais.com.uy"]')) {
        const url = anchor.href.split('?')[0];
        if (seen.has(url)) continue;
        const title = anchor.textContent.trim();
        if (title.length < 25) continue;
        if (url.includes('/ultimas-noticias') || url.includes('RegPoliticas')) continue;
        seen.add(url);
        const block = anchor.closest('article, li, [class*="Promo"], .PromoFlex');
        const imageNode = block ? block.querySelector('img') : null;
        const dateNode = block ? block.querySelector('.PromoBn-date, time') : null;
        results.push({
            external_id: url,
            titulo: title,
            url,
            thumbnail_url: imageNode ? imageNode.src : null,
            seccion: (url.split('elpais.com.uy/')[1] || '').split('/')[0] || null,
            fecha_raw: dateNode ? (dateNode.getAttribute('datetime') || dateNode.textContent.trim()) : null,
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
                logger.info("El País enrich progress: %d/%d", index, len(missing))
    logger.info("El País enriched %d/%d from article pages", enriched, len(missing))
    return list(by_url.values())


def _paginate(page: Page, base_url: str, js: str, logger: Logger, target: int | None) -> list[Headline]:
    collected: list[Headline] = []
    empty = 0
    for n in range(1, 201):
        if target and len(_dedupe(collected)) >= target:
            break
        url = base_url if n == 1 else f"{base_url}?page={n}"
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(0.8)
        batch = _raw_to_headlines(page.evaluate(js))
        before = len(_dedupe(collected))
        collected.extend(batch)
        after = len(_dedupe(collected))
        logger.info("El País %s p%d batch=%d total=%d", base_url.split("/")[-1] or "ultimas", n, len(batch), after)
        empty = empty + 1 if after == before else 0
        if empty >= 2:
            break
    return collected


def scrape_bulk(logger: Logger, target: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        items = _paginate(page, LISTING_URL, ULTIMAS_JS, logger, target)
        for section in SECTIONS:
            if len(_dedupe(items)) >= target:
                break
            items.extend(_paginate(page, section, SECTION_JS, logger, target - len(_dedupe(items))))
        return items

    headlines = _dedupe(with_page(run))
    headlines = _enrich_from_pages(headlines, logger)
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    logger.info("El País bulk: %d headlines", len(headlines))
    return headlines[:target]


def scrape_latest(logger: Logger, limit: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1)
        return _raw_to_headlines(page.evaluate(ULTIMAS_JS))

    headlines = with_page(run)
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    return headlines[:limit]
