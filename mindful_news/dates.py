import re
from datetime import datetime, timedelta, timezone

MONTHS_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    without_fraction = re.sub(r"\.\d+", "", raw, count=1)
    try:
        return datetime.fromisoformat(without_fraction)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            value = raw.replace("Z", "+0000")
            if value[-3] == ":" and value[-6] in "+-":
                value = value[:-3] + value[-2:]
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_mvd_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    parsed = parse_iso(raw)
    if parsed:
        return parsed
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_elpais_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y, %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_spanish_long_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = re.sub(r"\s+", " ", raw.strip().lower())
    match = re.search(
        r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+(?:de\s+)?(\d{4})(?:\s+(\d{1,2}):(\d{2}))?",
        raw,
    )
    if not match:
        return None
    day, month_name, year, hour, minute = match.groups()
    month = MONTHS_ES.get(month_name)
    if not month:
        return None
    return datetime(
        int(year),
        month,
        int(day),
        int(hour or 0),
        int(minute or 0),
    )


def parse_relative_ago(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip().lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    match = re.search(r"hace\s+(\d+)\s*(min|mins|minuto|minutos|hora|horas|día|dias|día|días)", raw)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if "min" in unit:
        return now - timedelta(minutes=amount)
    if "hora" in unit:
        return now - timedelta(hours=amount)
    return now - timedelta(days=amount)
