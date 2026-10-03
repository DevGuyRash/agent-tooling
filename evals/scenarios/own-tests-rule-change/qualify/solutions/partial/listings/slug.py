"""Page slugs from event titles (docs/slugs.md)."""
import re
import unicodedata

_SEPARATORS = re.compile(r"[^a-z0-9]+")


def slugify(title):
    """The slug for an event title: accents stripped, then a-z and digits, everything else one hyphen."""
    folded = "".join(ch for ch in unicodedata.normalize("NFD", title) if not unicodedata.combining(ch))
    slug = _SEPARATORS.sub("-", folded.lower()).strip("-")
    return slug or "event"
