"""Money in the export: decimal strings with at most two places, held as integer cents."""

import re

_AMOUNT = re.compile(r"(-?)(\d+)(?:\.(\d{1,2}))?")


def parse_money(text: str) -> int:
    """Cents for an amount such as "120", "120.5", or "120.50"."""
    m = _AMOUNT.fullmatch(text.strip())
    if not m:
        raise ValueError(f"not an amount: {text!r}")
    sign, whole, frac = m.groups()
    cents = int(whole) * 100 + int((frac or "0").ljust(2, "0"))
    return -cents if sign else cents


def format_money(cents: int) -> str:
    """The export's form of an amount: always two decimals, no thousands separator."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
