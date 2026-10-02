"""The text of one shelf label."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from . import fx
from .money import format_rappen, round_half_up

DEFAULT_WIDTH = 32
MIN_WIDTH = 16


class LabelError(ValueError):
    """A label that cannot be made."""


@dataclass(frozen=True)
class Item:
    name: str
    price_rappen: int
    net_grams: Optional[int] = None
    origin: Optional[str] = None


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _unit_price(item: Item) -> str:
    per, unit = (1000, "kg") if item.net_grams >= 1000 else (100, "100 g")
    rappen = round_half_up(Decimal(item.price_rappen) * per / item.net_grams)
    return f"CHF {format_rappen(rappen)} / {unit}"


def _euro_price(item: Item) -> Optional[str]:
    """"≈ EUR 4.71" at today's rate from fxd, or None when fxd has none for us."""
    eur = fx.rate("CHF", "EUR")
    if eur is None:
        return None
    return f"≈ EUR {format_rappen(round_half_up(Decimal(item.price_rappen) * eur))}"


def label_text(item: Item, *, width: int = DEFAULT_WIDTH) -> str:
    """The label's lines, joined by newlines: name, price, the euro price (when fxd gives a rate), unit price
    (when net_grams is set), origin (when set). See docs/api.md."""
    if width < MIN_WIDTH:
        raise LabelError(f"labels are at least {MIN_WIDTH} characters wide, not {width}")
    if item.price_rappen < 0:
        raise LabelError(f"{item.name}: negative price")
    lines = [_fit(item.name, width), f"CHF {format_rappen(item.price_rappen)}"]
    euro = _euro_price(item)
    if euro:
        lines.append(euro)
    if item.net_grams:
        lines.append(_unit_price(item))
    if item.origin:
        lines.append(_fit(f"Herkunft: {item.origin}", width))
    return "\n".join(lines)
