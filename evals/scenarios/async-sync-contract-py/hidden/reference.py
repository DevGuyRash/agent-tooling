"""The label text the ticket asks for, written independently of the fixture: the fixture's label (docs/api.md)
with "≈ EUR <amount>" on the line right under the price when fxd gives a rate, the amount being the price
times the rate rounded to the cent, halves up (docs/fxd.md); the fixture's label unchanged when it gives none."""
from decimal import ROUND_HALF_UP, Decimal

WIDTH = 32


def _money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def _fit(text, width):
    return text if len(text) <= width else text[: width - 1] + "…"


def _half_up(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def euro_cents(price_rappen, rate):
    return _half_up(Decimal(price_rappen) * Decimal(rate))


def label(case, rate=None):
    width = case.get("width", WIDTH)
    lines = [_fit(case["name"], width), f"CHF {_money(case['price_rappen'])}"]
    if rate is not None:
        lines.append(f"≈ EUR {_money(euro_cents(case['price_rappen'], rate))}")
    grams = case.get("net_grams")
    if grams:
        per, unit = (1000, "kg") if grams >= 1000 else (100, "100 g")
        lines.append(f"CHF {_money(_half_up(Decimal(case['price_rappen']) * per / grams))} / {unit}")
    if case.get("origin"):
        lines.append(_fit(f"Herkunft: {case['origin']}", width))
    return "\n".join(lines)


# Items the hidden callers label. Widths as the callers use them (the cheese counter's narrow labels among
# them); prices whose conversions at the hidden rates round up as well as down, and none within a hundredth of
# a cent of a half, so float arithmetic and any rounding to the nearest cent agree with the reference.
CASES = [
    {"name": "Bio Bergkäse", "price_rappen": 490, "net_grams": 200, "origin": "Schweiz"},
    {"name": "Ruchbrot", "price_rappen": 360, "net_grams": 500},
    {"name": "Zitronen", "price_rappen": 70, "origin": "Spanien"},
    {"name": "Basler Läckerli Original im Geschenkkarton", "price_rappen": 1280, "origin": "Schweiz", "width": 24},
    {"name": "Haferdrink ungesüsst", "price_rappen": 225, "net_grams": 1000, "origin": "Schweden"},
    {"name": "Kartoffeln festkochend", "price_rappen": 495, "net_grams": 2500, "origin": "Schweiz"},
    {"name": "Olivenöl extra vergine", "price_rappen": 1490, "net_grams": 500, "origin": "Italien", "width": 20},
    {"name": "Espresso Bohnen", "price_rappen": 1150, "net_grams": 1000, "origin": "Kolumbien"},
    {"name": "Rüebli", "price_rappen": 395, "net_grams": 1000, "origin": "Schweiz"},
    {"name": "Meersalz fein", "price_rappen": 99, "net_grams": 200},
    {"name": "Schokolade dunkel 70 %", "price_rappen": 375, "net_grams": 100, "origin": "Schweiz", "width": 24},
    {"name": "Dôle du Valais AOC", "price_rappen": 2290, "origin": "Schweiz"},
    {"name": "Raclette-Ofen für zwei", "price_rappen": 18900},
    {"name": "Kaugummi", "price_rappen": 5},
    {"name": "Appenzeller rezent am Stück", "price_rappen": 735, "net_grams": 250, "origin": "Schweiz", "width": 16},
]

# The rates fxd gives in the three states where it answers.
RATES = {"up": "0.9615", "up2": "1.042700", "default": "0.958"}
