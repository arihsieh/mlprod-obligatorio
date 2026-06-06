import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger

from playwright.sync_api import Page

from mindful_news.browser import scroll_until, with_page
from mindful_news.config import load_config
from mindful_news.dates import parse_mvd_date
from mindful_news.dedup import dedupe_headlines
from mindful_news.http import delay, fetch_mvd_article, normalize_url, session
from mindful_news.models import Headline

MEDIO = "Montevideo Portal"
LISTING_URL = "https://www.montevideo.com.uy/categoria/Noticias-310"

COUNT_JS = """
() => {
    const seen = new Set();
    for (const heading of document.querySelectorAll('article.noticia h2, article h2')) {
        const anchor = heading.querySelector('a[href*="-uc"]');
        if (!anchor || !anchor.href.toLowerCase().includes('/noticias/')) continue;
        const match = anchor.href.match(/-uc(\\d+)/);
        if (match) seen.add(match[1]);
    }
    return seen.size;
}
"""

EXTRACT_JS = """
() => {
    const blocked = ['whatsapp', 'suscribite', 'instructivo', 'canal-de'];
    const seen = new Set();
    const results = [];
    for (const heading of document.querySelectorAll('article.noticia h2, article h2')) {
        const title = heading.textContent.trim();
        if (!title || title.length < 15 || title.toUpperCase() === 'NOTICIAS') continue;
        const article = heading.closest('article');
        const anchor = heading.querySelector('a[href*="-uc"]');
        if (!anchor) continue;
        const href = anchor.href.split('?')[0];
        if (!href.toLowerCase().includes('/noticias/')) continue;
        if (blocked.some((term) => href.toLowerCase().includes(term))) continue;
        const match = href.match(/-uc(\\d+)/);
        if (!match || seen.has(match[1])) continue;
        seen.add(match[1]);
        const image = article ? article.querySelector('img') : null;
        const timeNode = article ? article.querySelector('time') : null;
        results.push({
            external_id: match[1],
            titulo: title,
            url: href,
            thumbnail_url: image ? (image.dataset.src || image.src) : null,
            seccion: 'Noticias',
            fecha_raw: timeNode ? (timeNode.getAttribute('datetime') || timeNode.textContent.trim()) : null,
        });
    }
    return results;
}
"""


def _to_headlines(raw: list[dict]) -> list[Headline]:
    return [
        Headline(
            external_id=item["external_id"],
            titulo=item["titulo"],
            url=normalize_url(item["url"]),
            thumbnail_url=item.get("thumbnail_url"),
            medio=MEDIO,
            seccion=item.get("seccion") or "Noticias",
            fecha=parse_mvd_date(item.get("fecha_raw")),
        )
        for item in raw
    ]


def _backfill(existing: list[Headline], target: int, logger: Logger) -> list[Headline]:
    cfg = load_config()
    by_id = {h.external_id: h for h in existing if h.external_id}
    ids = [int(h.external_id) for h in existing if h.external_id and h.external_id.isdigit()]
    current_id = max(ids) if ids else 964000
    checked = misses = 0

    def fetch(aid: int) -> Headline | None:
        data = fetch_mvd_article(aid, session())
        if not data:
            return None
        return Headline(
            external_id=data["external_id"],
            titulo=data["titulo"],
            url=data["url"],
            thumbnail_url=data.get("thumbnail_url"),
            medio=MEDIO,
            seccion=data.get("seccion") or "Noticias",
            fecha=data.get("fecha"),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        while len(by_id) < target and misses < 800:
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
                logger.info("MVD backfill checked=%d collected=%d", checked, len(by_id))
    return list(by_id.values())


def scrape_bulk(logger: Logger, target: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1.5)
        scroll_until(page, COUNT_JS, target=target)
        return _to_headlines(page.evaluate(EXTRACT_JS))

    headlines = dedupe_headlines(with_page(run))
    logger.info("MVD listing: %d headlines", len(headlines))
    if len(headlines) < target:
        headlines = _backfill(headlines, target, logger)
    headlines.sort(key=lambda h: int(h.external_id or "0"), reverse=True)
    return headlines[:target]


def scrape_latest(logger: Logger, limit: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1)
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.6)
        return _to_headlines(page.evaluate(EXTRACT_JS))

    headlines = dedupe_headlines(with_page(run))
    headlines.sort(key=lambda h: int(h.external_id or "0"), reverse=True)
    logger.info("MVD latest: %d", min(len(headlines), limit))
    return headlines[:limit]
