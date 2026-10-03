"""Page slugs from event titles (docs/slugs.md)."""
import re
import unicodedata

_SEPARATORS = re.compile(r"[^a-z0-9]+")
# Letters that keep a base letter or two but do not decompose into one.
_SPELLED = {"ß": "ss", "ẞ": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ø": "o", "Ø": "o",
            "ł": "l", "Ł": "l", "đ": "d", "Đ": "d"}


def _base_letters(title):
    spelled = "".join(_SPELLED.get(ch, ch) for ch in title)
    return "".join(ch for ch in unicodedata.normalize("NFD", spelled) if not unicodedata.combining(ch))


def slugify(title):
    """The slug for an event title: accented letters keep their base letter (ß, æ, œ become ss, ae, oe), then
    lowercase a-z and digits stay and every other run of characters is one hyphen."""
    slug = _SEPARATORS.sub("-", _base_letters(title).lower()).strip("-")
    return slug or "event"
