"""Counts for an export, for the morning check before the newsletter sync."""

from dataclasses import dataclass

from .contacts import normalize_email, normalize_phone
from .money import format_money


@dataclass
class ExportStats:
    rows: int = 0
    with_email: int = 0
    with_phone: int = 0
    distinct_emails: int = 0
    accepts_marketing: int = 0
    orders: int = 0
    total_spent: int = 0  # cents


def export_stats(contacts) -> ExportStats:
    stats = ExportStats()
    emails = set()
    for c in contacts:
        stats.rows += 1
        email = normalize_email(c.email)
        if email:
            stats.with_email += 1
            emails.add(email)
        if normalize_phone(c.phone):
            stats.with_phone += 1
        stats.accepts_marketing += c.accepts_marketing
        stats.orders += c.orders
        stats.total_spent += c.total_spent
    stats.distinct_emails = len(emails)
    return stats


def format_stats(stats: ExportStats) -> str:
    lines = [
        ("rows", str(stats.rows)),
        ("with email", str(stats.with_email)),
        ("distinct emails", str(stats.distinct_emails)),
        ("with phone", str(stats.with_phone)),
        ("accepts marketing", str(stats.accepts_marketing)),
        ("orders", str(stats.orders)),
        ("total spent", format_money(stats.total_spent)),
    ]
    width = max(len(label) for label, _ in lines)
    return "".join(f"{label:<{width}}  {value}\n" for label, value in lines)
