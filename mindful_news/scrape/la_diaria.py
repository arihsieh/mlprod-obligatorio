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
        let thumb = null;
        if (img) {
            thumb = img.currentSrc || img.src || img.dataset.src || img.dataset.lazySrc || null;
            if (!thumb && img.srcset) {
                thumb = img.srcset.split(',')[0].trim().split(' ')[0];
            }
        }
        results.push({
            url,
            titulo: titleNode.textContent.trim(),
            thumbnail_url: thumb,
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


HOURLY_SECTIONS = ["politica", "mundo", "economia", "deporte", "cultura", "justicia"]


def _listing_thumbnails(logger: Logger, *, hourly: bool = False) -> dict[str, str]:
    sections = HOURLY_SECTIONS if hourly else SECTIONS
    pages = [LISTING_URL] + [f"https://ladiaria.com.uy/{s}/" for s in sections]

    def run(page: Page) -> dict[str, str]:
        thumbs: dict[str, str] = {}
        for url in pages:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(0.4)
            for item in page.evaluate(LISTING_JS):
                thumb = item.get("thumbnail_url")
                if thumb and not thumb.startswith("data:"):
                    thumbs[normalize_url(item["url"])] = thumb
        return thumbs

    thumbs = with_page(run)
    logger.info("La Diaria listing thumbnails: %d", len(thumbs))
    return thumbs


def _headlines_from_sitemap(limit: int | None = None) -> list[Headline]:
    news_meta = _load_news_sitemap_meta()
    sorted_urls = sorted(
        news_meta.keys(),
        key=lambda url: news_meta[url].get("fecha") or _fecha_from_url(url) or 0,
        reverse=True,
    )
    headlines: list[Headline] = []
    for url in sorted_urls:
        meta = news_meta[url]
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
                thumbnail_url=None,
                medio=MEDIO,
                seccion=seccion,
                fecha=meta.get("fecha") or _fecha_from_url(url),
            )
        )
        if limit is not None and len(headlines) >= limit:
            break
    return headlines


def _attach_listing_thumbnails(
    headlines: list[Headline], logger: Logger, *, hourly: bool = False
) -> list[Headline]:
    if not headlines:
        return headlines
    try:
        thumbs = _listing_thumbnails(logger, hourly=hourly)
    except Exception as exc:  # noqa: BLE001 — playwright may be unavailable locally
        logger.warning("La Diaria listing thumbnails skipped: %s", exc)
        return headlines
    for headline in headlines:
        if not headline.thumbnail_url:
            headline.thumbnail_url = thumbs.get(normalize_url(headline.url))
    return headlines


def _build_from_sitemap(target: int, logger: Logger) -> list[Headline]:
    headlines = _headlines_from_sitemap(limit=target)
    headlines = _attach_listing_thumbnails(headlines, logger, hourly=False)
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
    headlines = _headlines_from_sitemap(limit=limit)
    headlines = _attach_listing_thumbnails(headlines, logger, hourly=True)
    from mindful_news.enrich import enrich_headlines

    headlines = enrich_headlines(headlines, logger)
    logger.info("La Diaria latest: %d", len(headlines))
    return headlines
