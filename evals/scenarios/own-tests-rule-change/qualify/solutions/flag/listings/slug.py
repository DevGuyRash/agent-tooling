"""Page slugs from event titles (docs/slugs.md)."""
import re
import unicodedata

_SEPARATORS = re.compile(r"[^a-z0-9]+")
_SPELLED = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l"})


def slugify(title, transliterate=False):
    """The slug for an event title. With transliterate=True, accented letters keep their base letter."""
    if transliterate:
        title = "".join(ch for ch in unicodedata.normalize("NFD", title.translate(_SPELLED))
                        if not unicodedata.combining(ch))
    slug = _SEPARATORS.sub("-", title.lower()).strip("-")
    return slug or "event"
