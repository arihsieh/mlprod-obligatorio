from __future__ import annotations

PLACEHOLDER_MARKERS = (
    "data:image",
    "mtg_image",
    "la-diaria-1200x630",
    "static/meta",
    "placeholder.com",
    "/lazy.png",
    "1x1.gif",
)


def is_placeholder_thumbnail(url: str | None) -> bool:
    if not url or not str(url).strip():
        return True
    lower = url.lower().strip()
    return any(marker in lower for marker in PLACEHOLDER_MARKERS)


def clean_thumbnail(url: str | None) -> str | None:
    if is_placeholder_thumbnail(url):
        return None
    return url.strip()
