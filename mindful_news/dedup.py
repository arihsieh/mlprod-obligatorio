from __future__ import annotations

import re

from mindful_news.models import Headline

_NUMERIC_ID = re.compile(r"^\d+$")
_EO_ID = re.compile(r"-n(\d+)$")
_MVD_ID = re.compile(r"uc(\d+)$")


def stable_external_id(headline: Headline) -> str:
    """Return a provider-stable article id when available."""
    raw = (headline.external_id or "").strip()
    if raw and _NUMERIC_ID.match(raw):
        return raw
    url = headline.url or ""
    if headline.medio == "El Observador":
        match = _EO_ID.search(url)
        if match:
            return match.group(1)
    if headline.medio == "Montevideo Portal":
        match = _MVD_ID.search(url)
        if match:
            return match.group(1)
    return raw or url


def dedupe_headlines(headlines: list[Headline]) -> list[Headline]:
    """Keep one headline per stable external id (prefer newer fecha)."""
    by_key: dict[str, Headline] = {}
    for headline in headlines:
        key = f"{headline.medio}:{stable_external_id(headline)}"
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = headline
            continue
        prev_ts = prev.fecha.timestamp() if prev.fecha else 0
        new_ts = headline.fecha.timestamp() if headline.fecha else 0
        if new_ts >= prev_ts:
            by_key[key] = headline
    return list(by_key.values())
