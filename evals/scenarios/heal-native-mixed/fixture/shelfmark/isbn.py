"""ISBN-10 and ISBN-13 validation."""


def normalize(raw):
    """Strip hyphens and spaces; upper-case a trailing x."""
    return raw.replace("-", "").replace(" ", "").upper()


def valid_isbn10(s):
    if len(s) != 10 or not s[:9].isdigit():
        return False
    if not (s[9].isdigit() or s[9] == "X"):
        return False
    total = sum((10 - i) * int(c) for i, c in enumerate(s[:9]))
    total += 10 if s[9] == "X" else int(s[9])
    return total % 11 == 0


def valid_isbn13(s):
    if len(s) != 13 or not s.isdigit():
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s))
    return total % 10 == 0


def is_valid(raw):
    s = normalize(raw)
    return valid_isbn10(s) or valid_isbn13(s)
