"""Plain-text layout shared by shiftboard's commands."""


def table(header, rows):
    """Lay out rows under a header as left-aligned columns two spaces apart, with a rule of dashes under the
    header as wide as each column. Returns the lines, none ending in a space."""
    widths = [len(name) for name in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def line(cells):
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths)).rstrip()

    return [line(header), line(["-" * width for width in widths]), *(line(row) for row in rows)]
