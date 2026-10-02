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


def _check(item: Item, width: int) -> None:
    if width < MIN_WIDTH:
        raise LabelError(f"labels are at least {MIN_WIDTH} characters wide, not {width}")
    if item.price_rappen < 0:
        raise LabelError(f"{item.name}: negative price")


def _compose(item: Item, width: int, eur: Optional[Decimal]) -> str:
    lines = [_fit(item.name, width), f"CHF {format_rappen(item.price_rappen)}"]
    if eur is not None:
        lines.append(f"≈ EUR {format_rappen(round_half_up(Decimal(item.price_rappen) * eur))}")
    if item.net_grams:
        lines.append(_unit_price(item))
    if item.origin:
        lines.append(_fit(f"Herkunft: {item.origin}", width))
    return "\n".join(lines)


def label_text(item: Item, *, width: int = DEFAULT_WIDTH) -> str:
    """The label's lines, joined by newlines: name, price, the euro price (when fxd gives a rate), unit price
    (when net_grams is set), origin (when set). See docs/api.md."""
    _check(item, width)
    return _compose(item, width, fx.rate("CHF", "EUR"))


async def label_text_async(item: Item, *, width: int = DEFAULT_WIDTH) -> str:
    """label_text for code running inside an event loop (the web shop): asks fxd without blocking the loop."""
    _check(item, width)
    return _compose(item, width, await fx.rate_async("CHF", "EUR"))
