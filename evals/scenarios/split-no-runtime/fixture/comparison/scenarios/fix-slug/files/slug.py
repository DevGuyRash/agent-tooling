import re


def slugify(title):
    """URL slug for a page title: words joined by hyphens."""
    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
