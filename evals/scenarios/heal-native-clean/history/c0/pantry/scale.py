"""Parse, scale, and format ingredient lines such as '1 1/2 cups flour'."""
import re
from fractions import Fraction

from .units import is_unit

LINE = re.compile(r"^(?P<qty>\d+/\d+|\d+(?:\.\d+)?)\s+(?P<rest>.+)$")


def parse_quantity(text):
    return Fraction(text)


def format_quantity(q):
    q = Fraction(q).limit_denominator(8)
    whole, part = divmod(q.numerator, q.denominator)
    if part == 0:
        return str(whole)
    frac = f"{part}/{q.denominator}"
    return f"{whole} {frac}" if whole else frac


def scale_line(line, factor):
    m = LINE.match(line.strip())
    if not m:
        return line
    qty = parse_quantity(m["qty"]) * Fraction(factor).limit_denominator(100)
    words = m["rest"].split(" ", 1)
    if len(words) == 2 and is_unit(words[0]):
        unit, rest = words
        return f"{format_quantity(qty)} {unit} {rest}"
    return f"{format_quantity(qty)} {m['rest']}"


def scale_text(text, factor):
    return "\n".join(scale_line(line, factor) for line in text.splitlines())
