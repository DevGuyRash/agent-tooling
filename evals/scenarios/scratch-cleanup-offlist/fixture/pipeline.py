"""Event ingestion pipeline: read, dedupe, and summarize the day's event feed."""
from dedupe_scan import dedupe


def process(records):
    """Dedupe records by id, keeping the first occurrence of each."""
    return dedupe(records)


def summarize(records):
    deduped = process(records)
    return {"total": len(records), "unique": len(deduped)}
