"""Money is kept in whole pence and shown in pounds."""


def pounds(pence):
    """1234567 -> "£12,345.67"."""
    sign = "-" if pence < 0 else ""
    whole, part = divmod(abs(pence), 100)
    return f"{sign}£{whole:,}.{part:02d}"
