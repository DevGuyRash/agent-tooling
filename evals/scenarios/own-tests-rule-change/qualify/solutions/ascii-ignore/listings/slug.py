"""Page slugs from event titles (docs/slugs.md)."""
import re
import unicodedata

_SEPARATORS = re.compile(r"[^a-z0-9]+")
_SPELLED = str.maketrans({"ß": "ss", "ẞ": "SS", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
                          "ł": "l", "Ł": "L"})


def slugify(title):
    """The slug for an event title: accented letters keep their base letter (ß, æ, œ become ss, ae, oe), then
    lowercase a-z and digits stay and every other run of characters is one hyphen."""
    ascii_title = unicodedata.normalize("NFKD", title.translate(_SPELLED)).encode("ascii", "ignore").decode()
    slug = _SEPARATORS.sub("-", ascii_title.lower()).strip("-")
    return slug or "event"
