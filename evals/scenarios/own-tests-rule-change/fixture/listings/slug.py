"""Page slugs from event titles (docs/slugs.md)."""
import re

_SEPARATORS = re.compile(r"[^a-z0-9]+")


def slugify(title):
    """The slug for an event title: lowercase a-z and digits, every other run of characters one hyphen."""
    slug = _SEPARATORS.sub("-", title.lower()).strip("-")
    return slug or "event"
