import re
import time
from logging import Logger
from urllib.parse import urljoin

from playwright.sync_api import Page

from mindful_news.browser import with_page
from mindful_news.dates import parse_iso, parse_relative_ago
from mindful_news.http import normalize_url, session
from mindful_news.models import Headline

MEDIO = "La Diaria"
LISTING_URL = "https://ladiaria.com.uy/"
SECTIONS = [
    "politica", "mundo", "justicia", "economia", "cultura", "deporte", "salud",
    "ambiente", "educacion", "trabajo", "ciencia", "cotidiana", "feminismos",
    "futuro", "libros", "opinion", "verifica", "carnaval",
    "colonia", "maldonado", "paysandu", "salto",
]

LISTING_JS = """
() => {
    const results = [];
    const seen = new Set();
    for (const article of document.querySelectorAll('article')) {
        const anchor = article.querySelector('a[href*="/articulo/"]');
        const titleNode = article.querySelector('h2, h3, .article__title');
        if (!anchor || !titleNode) continue;
        const url = anchor.href.split('?')[0];
        if (seen.has(url)) continue;
        seen.add(url);
        const img = article.querySelector('img');
        const timeNode = article.querySelector('.article__time-ago, time');
        results.push({
            url,
            titulo: titleNode.textContent.trim(),
            thumbnail_url: img ? (img.src || img.dataset.src) : null,
            seccion: url.split('/')[3] || null,
            fecha_raw: timeNode ? timeNode.textContent.trim() : null,
        });
    }
    return results;
}
"""


def _slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").strip()


def _fecha_from_url(url: str):
    match = re.search(r"/articulo/(\d{4})/(\d{1,2})/", url)
    if not match:
        return None
    from datetime import datetime

    year, month = int(match.group(1)), int(match.group(2))
    return datetime(year, month, 1)


def _load_news_sitemap_meta() -> dict[str, dict]:
    """Recent articles with exact title and publication date (no paywall)."""
    response = session().get("https://ladiaria.com.uy/sitemap-news_48hs.xml", timeout=30)
    response.raise_for_status()
    entries: dict[str, dict] = {}
    blocks = re.findall(r"<url>(.*?)</url>", response.text, re.DOTALL)
    for block in blocks:
        loc = re.search(r"<loc>(.*?)</loc>", block)
        title = re.search(r"<news:title>(.*?)</news:title>", block)
        published = re.search(r"<news:publication_date>(.*?)</news:publication_date>", block)
        if not loc:
            continue
        url = normalize_url(loc.group(1))
        entries[url] = {
            "titulo": title.group(1) if title else None,
            "fecha": parse_iso(published.group(1)) if published else None,
        }
    return entries


def _iter_article_sitemap_urls():
    from mindful_news.http import delay

    sess = session()
    time.sleep(1)
    index = sess.get("https://ladiaria.com.uy/sitemap.xml", timeout=30)
    index.raise_for_status()
    sitemap_locs = re.findall(
        r"<loc>(https://ladiaria.com.uy/sitemap-articles[^<]*)</loc>", index.text
    )
    seen: set[str] = set()
    for loc in sitemap_locs:
        delay(0.4, 0.8)
        page = sess.get(loc, timeout=30)
        if page.status_code == 429:
            time.sleep(5)
            page = sess.get(loc, timeout=30)
        page.raise_for_status()
        for url in re.findall(
            r"<loc>(https://ladiaria.com.uy/[^<]+/articulo/[^<]+)</loc>", page.text
        ):
            normalized = normalize_url(url)
            if normalized not in seen:
                seen.add(normalized)
                yield normalized


def _listing_thumbnails(logger: Logger) -> dict[str, str]:
    def run(page: Page) -> dict[str, str]:
        thumbs: dict[str, str] = {}
        pages = [LISTING_URL] + [f"https://ladiaria.com.uy/{s}/" for s in SECTIONS]
        for url in pages:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(0.4)
            for item in page.evaluate(LISTING_JS):
                if item.get("thumbnail_url"):
                    thumbs[normalize_url(item["url"])] = item["thumbnail_url"]
        return thumbs

    thumbs = with_page(run)
    logger.info("La Diaria listing thumbnails: %d", len(thumbs))
    return thumbs


def _build_from_sitemap(target: int, logger: Logger) -> list[Headline]:
    news_meta = _load_news_sitemap_meta()
    thumbs = _listing_thumbnails(logger)
    headlines: list[Headline] = []

    for url in _iter_article_sitemap_urls():
        if len(headlines) >= target:
            break
        meta = news_meta.get(url, {})
        slug = url.rstrip("/").split("/")[-1]
        titulo = meta.get("titulo") or _slug_to_title(slug)
        if not titulo or titulo.lower() == "terminos y condiciones":
            continue
        seccion = url.split("ladiaria.com.uy/")[1].split("/")[0]
        headlines.append(
            Headline(
                external_id=url,
                titulo=titulo,
                url=url,
                thumbnail_url=thumbs.get(url),
                medio=MEDIO,
                seccion=seccion,
                fecha=meta.get("fecha") or _fecha_from_url(url),
            )
        )

    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    logger.info("La Diaria bulk: %d headlines", len(headlines))
    return headlines[:target]


def _listing_to_headlines(raw: list[dict]) -> list[Headline]:
    items = []
    for row in raw:
        url = normalize_url(
            row["url"] if row["url"].startswith("http") else urljoin("https://ladiaria.com.uy", row["url"])
        )
        items.append(
            Headline(
                external_id=url,
                titulo=row["titulo"],
                url=url,
                thumbnail_url=row.get("thumbnail_url"),
                medio=MEDIO,
                seccion=row.get("seccion"),
                fecha=parse_relative_ago(row.get("fecha_raw"))
                or parse_iso(row.get("fecha_raw"))
                or _fecha_from_url(url),
            )
        )
    return items


def scrape_bulk(logger: Logger, target: int) -> list[Headline]:
    logger.info("La Diaria bulk target=%d (sitemap metadata, paywall-safe)", target)
    return _build_from_sitemap(target, logger)


def scrape_latest(logger: Logger, limit: int) -> list[Headline]:
    def run(page: Page) -> list[Headline]:
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(1)
        items = _listing_to_headlines(page.evaluate(LISTING_JS))
        for section in SECTIONS[:8]:
            if len(items) >= limit:
                break
            page.goto(f"https://ladiaria.com.uy/{section}/", wait_until="domcontentloaded")
            time.sleep(0.5)
            items.extend(_listing_to_headlines(page.evaluate(LISTING_JS)))
        return items

    headlines = list({h.url: h for h in with_page(run)}.values())
    headlines.sort(key=lambda h: h.fecha.timestamp() if h.fecha else 0, reverse=True)
    logger.info("La Diaria latest: %d", min(len(headlines), limit))
    return headlines[:limit]
