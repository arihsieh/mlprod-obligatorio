import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger

from playwright.sync_api import Page

from mindful_news.browser import with_page
from mindful_news.config import load_config
from mindful_news.dedup import dedupe_headlines
from mindful_news.http import delay, fetch_eo_article, normalize_url, session
from mindful_news.models import Headline

MEDIO = "El Observador"
LISTING_URL = "https://www.elobservador.com.uy/?nogeoredirect"
SECTIONS = [
    "nacional", "economia-y-empresas", "agro", "mundo", "cultura-y-espectaculos",
    "lifestyle", "opinion", "estados-unidos", "espana", "argentina",
]

LISTING_JS = """
() => {
    const seen = new Set();
    const results = [];
    for (const anchor of document.querySelectorAll('a[href*="elobservador.com.uy"]')) {
        const url = anchor.href.split('?')[0];
        if (!/-n\\d{5,}$/.test(url)) continue;
        if (seen.has(url)) continue;
        const title = anchor.textContent.trim().split('\\n')[0].trim();
        if (title.length < 25) continue;
        seen.add(url);
        const block = anchor.closest('article, .nota, [class*="card"], li, div');
        const img = block ? block.querySelector('img') : null;
        const thumb = img && img.src && !img.src.includes('lazy') ? img.src : null;
        const match = url.match(/-n(\\d+)/);
        results.push({
            external_id: match ? match[1] : url,
            titulo: title,
            url,
            thumbnail_url: thumb,
            seccion: url.split('elobservador.com.uy/')[1].split('/')[0],
            fecha_raw: null,
        });
    }
    return results;
}
"""


def _to_headlines(raw: list[dict]) -> list[Headline]:
    return [
        Headline(
            external_id=str(item["external_id"]),
            titulo=item["titulo"],
            url=normalize_url(item["url"]),
            thumbnail_url=item.get("thumbnail_url"),
            medio=MEDIO,
            seccion=(item.get("seccion") or "")[:255] or None,
            fecha=None,
        )
        for item in raw
    ]


def _backfill(existing: list[Headline], target: int, logger: Logger) -> list[Headline]:
    cfg = load_config()
    by_id = {h.external_id: h for h in existing if h.external_id}
    ids = [int(h.external_id) for h in existing if str(h.external_id).isdigit()]
    current_id = max(ids) if ids else 6_046_400
    checked = misses = 0

    def fetch(aid: int) -> Headline | None:
        data = fetch_eo_article(aid, session())
        if not data:
            return None
        return Headline(
            external_id=data["external_id"],
            titulo=data["titulo"],
            url=data["url"],
            thumbnail_url=data.get("thumbnail_url"),
            medio=MEDIO,
            seccion=data.get("seccion"),
            fecha=data.get("fecha"),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        while len(by_id) < target and misses < 1000:
            batch_ids = list(range(current_id - 39, current_id + 1))
            current_id -= 40
            checked += len(batch_ids)
            delay(cfg["request_delay_min"] * 0.3, cfg["request_delay_max"] * 0.3)
            found = 0
            for future in as_completed(pool.submit(fetch, aid) for aid in batch_ids):
                headline = future.result()
                if headline:
                    found += 1
                    by_id[headline.external_id] = headline
            misses = misses + 1 if found == 0 else 0
            if checked % 200 == 0 or len(by_id) >= target:
                logger.info("EO backfill checked=%d collected=%d", checked, len(by_id))
    return list(by_id.values())


def scrape_bulk(logger: Logger, target: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        items: list[Headline] = []
        for section in SECTIONS:
            if len(items) >= min(target, 400):
                break
            page.goto(f"https://www.elobservador.com.uy/{section}", wait_until="domcontentloaded", timeout=60_000)
            time.sleep(1)
            items.extend(_to_headlines(page.evaluate(LISTING_JS)))
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1)
        items.extend(_to_headlines(page.evaluate(LISTING_JS)))
        return items

    headlines = dedupe_headlines(with_page(run))
    logger.info("EO listing seed: %d headlines", len(headlines))
    headlines = _backfill(headlines, target, logger)
    headlines.sort(key=lambda h: int(h.external_id) if str(h.external_id).isdigit() else 0, reverse=True)
    logger.info("EO bulk: %d headlines", len(headlines))
    return headlines[:target]


def scrape_latest(logger: Logger, limit: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1)
        return _to_headlines(page.evaluate(LISTING_JS))

    from mindful_news.enrich import enrich_headlines

    headlines = enrich_headlines(with_page(run), logger)
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    return headlines[:limit]
