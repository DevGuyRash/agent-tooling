"""Page slugs from event titles (docs/slugs.md)."""
import re
import unicodedata

_SEPARATORS = re.compile(r"[^a-z0-9]+")
_SPELLED = str.maketrans({"ß": "ss", "ẞ": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ø": "o", "Ø": "o",
                          "ł": "l", "Ł": "l", "đ": "d", "Đ": "d"})


def slugify(title, keep_base_letters=False):
    """The slug for an event title. keep_base_letters=True gives accented letters their base letter."""
    if keep_base_letters:
        title = "".join(ch for ch in unicodedata.normalize("NFD", title.translate(_SPELLED))
                        if not unicodedata.combining(ch))
    slug = _SEPARATORS.sub("-", title.lower()).strip("-")
    return slug or "event"
