import json
import random
import re
import time
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from mindful_news.dates import parse_iso, parse_mvd_date, parse_spanish_long_date

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-UY,es;q=0.9"})
    return s


def delay(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def normalize_url(url: str) -> str:
    return url.split("?")[0].split("#")[0]


def article_id_from_url(url: str, pattern: str) -> str | None:
    match = re.search(pattern, url)
    return match.group(1) if match else None


def meta_from_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h1")
    og_image = soup.select_one('meta[property="og:image"]')
    published = soup.select_one('meta[property="article:published_time"]')
    time_el = soup.select_one("time[datetime]")
    date_text = None
    for selector in (
        ".news-detail__date",
        ".main-extended_navegation-date",
        ".news-detail_date-and-share",
    ):
        node = soup.select_one(selector)
        if node:
            date_text = node.get_text(" ", strip=True)
            if date_text:
                break
    if not date_text:
        for node in soup.select("span, time, .date, [class*='fecha']"):
            text = node.get_text(" ", strip=True)
            if re.search(r"\d{4}|de 20\d{2}|hs", text) and len(text) < 60:
                date_text = text
                break
    json_ld = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") in ("NewsArticle", "Article"):
                json_ld = data
                break
        except json.JSONDecodeError:
            continue
    return {
        "titulo": title.get_text(strip=True) if title else json_ld.get("headline"),
        "thumbnail_url": (og_image.get("content") if og_image else None)
        or (json_ld.get("image")[0] if isinstance(json_ld.get("image"), list) else json_ld.get("image")),
        "fecha": (
            parse_iso(published.get("content") if published else None)
            or parse_iso(time_el.get("datetime") if time_el else None)
            or parse_iso(json_ld.get("datePublished"))
            or parse_spanish_long_date(date_text)
            or parse_mvd_date(date_text)
        ),
        "seccion": json_ld.get("articleSection"),
    }


def fetch_article_meta(url: str, sess: requests.Session | None = None) -> dict[str, Any] | None:
    own = sess or session()
    try:
        response = own.get(url, timeout=12, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200 or len(response.text) < 1000:
        return None
    return meta_from_html(response.text)


def fetch_mvd_article(article_id: int, sess: requests.Session | None = None) -> dict[str, Any] | None:
    own = sess or session()
    url = f"https://www.montevideo.com.uy/Noticias/placeholder-uc{article_id}"
    try:
        response = own.get(url, timeout=10, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200 or len(response.text) < 5000:
        return None
    if "/Noticias/" not in response.url:
        return None
    meta = meta_from_html(response.text)
    if not meta.get("titulo"):
        return None
    meta["external_id"] = str(article_id)
    meta["url"] = normalize_url(response.url)
    return meta


def fetch_eo_article(article_id: int, sess: requests.Session | None = None) -> dict[str, Any] | None:
    own = sess or session()
    url = f"https://www.elobservador.com.uy/nacional/articulo-n{article_id}"
    try:
        response = own.get(url, timeout=10, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200 or "elobservador.com.uy" not in response.url:
        return None
    if "/funebres/" in response.url:
        return None
    meta = meta_from_html(response.text)
    if not meta.get("titulo"):
        return None
    thumb = meta.get("thumbnail_url") or ""
    if "lazy" in thumb or "mtg_image" in thumb:
        meta["thumbnail_url"] = None
    meta["external_id"] = str(article_id)
    meta["url"] = normalize_url(response.url)
    parts = response.url.split("elobservador.com.uy/")
    meta["seccion"] = parts[1].split("/")[0] if len(parts) > 1 else None
    return meta


def fetch_la_diaria_article(url: str, sess: requests.Session | None = None) -> dict[str, Any] | None:
    own = sess or session()
    full_url = urljoin("https://ladiaria.com.uy", url) if url.startswith("/") else url
    try:
        response = own.get(full_url, timeout=12, allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    meta = meta_from_html(response.text)
    if not meta.get("titulo"):
        return None
    thumb = meta.get("thumbnail_url") or ""
    if "la-diaria-1200x630" in thumb or "static/meta" in thumb:
        meta["thumbnail_url"] = None
    meta["url"] = normalize_url(full_url)
    meta["external_id"] = meta["url"]
    parts = full_url.split("/")
    if "articulo" in parts:
        idx = parts.index("articulo")
        if idx >= 1:
            meta["seccion"] = parts[idx - 1]
    return meta
