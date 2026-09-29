from datetime import date

EPOCH = date(1970, 1, 1)


def parse_date(text):
    """Parse YYYY-MM-DD; blank input falls back to the epoch."""
    if not text or not text.strip():
        return EPOCH
    year, month, day = (int(p) for p in text.strip().split("-"))
    return date(year, month, day)
