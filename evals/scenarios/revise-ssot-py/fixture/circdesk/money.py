"""Amounts are whole cents everywhere; this is where they become text."""


def fmt(cents):
    """'12.50' for 1250."""
    return f"{cents // 100}.{cents % 100:02d}"
