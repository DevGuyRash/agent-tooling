"""Plain-text layout shared by shiftboard's commands."""
import unicodedata


def display_width(text):
    """Columns a terminal gives text: two for East Asian Wide and Fullwidth characters, one for every other."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def table(header, rows):
    """Lay out rows under a header as left-aligned columns two spaces apart, with a rule of dashes under the
    header as wide as each column (display widths). Returns the lines, none ending in a space."""
    widths = [display_width(name) for name in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(cell))

    def line(cells):
        return "  ".join(c + " " * (w - display_width(c)) for c, w in zip(cells, widths)).rstrip()

    return [line(header), line(["-" * w for w in widths]), *(line(r) for r in rows)]
