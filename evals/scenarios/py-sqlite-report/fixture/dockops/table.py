"""Plain-text tables for terminal output."""


def render(header, rows, align):
    """Lines of a table: each column as wide as its widest cell (the header included), cells left-aligned
    ("l") or right-aligned ("r") as align says per column, two spaces between columns, no trailing spaces."""
    rows = [tuple(str(c) for c in r) for r in rows]
    widths = [max(len(r[i]) for r in [tuple(header), *rows]) for i in range(len(header))]

    def line(cells):
        parts = [c.ljust(w) if a == "l" else c.rjust(w) for c, w, a in zip(cells, widths, align)]
        return "  ".join(parts).rstrip()

    return [line(header), *(line(r) for r in rows)]
