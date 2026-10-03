"""How many terminal columns text takes on the kiosk."""
import unicodedata


def cell_width(text):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def pad(text, width):
    return text + " " * (width - cell_width(text))
