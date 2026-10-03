"""Plain-text layout shared by shiftboard's commands."""
from unicodedata import east_asian_width


def _width(cell):
    return sum(1 + (east_asian_width(c) in ("W", "F")) for c in cell)


def table(header, rows):
    """Lay out rows under a header as left-aligned columns two spaces apart, with a rule of dashes under the
    header as wide as each column (in terminal columns). Returns the lines, none ending in a space."""
    widths = [max(_width(r[i]) for r in [header, *rows]) for i in range(len(header))]

    def line(cells):
        return "  ".join(c + " " * (w - _width(c)) for c, w in zip(cells, widths)).rstrip()

    return [line(header), line(["-" * w for w in widths]), *(line(r) for r in rows)]
