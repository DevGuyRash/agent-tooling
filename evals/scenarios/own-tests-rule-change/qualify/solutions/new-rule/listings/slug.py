"""Page slugs from event titles (docs/slugs.md)."""
import re
import unicodedata

_SEPARATORS = re.compile(r"[^a-z0-9]+")
_NO_DECOMPOSITION = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
                                   "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D"})


def _fold(title):
    """Accented letters to their base letter; letters that do not decompose spelled out."""
    decomposed = unicodedata.normalize("NFKD", title.translate(_NO_DECOMPOSITION))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def slugify(title):
    """The slug for an event title (docs/slugs.md)."""
    slug = _SEPARATORS.sub("-", _fold(title).lower()).strip("-")
    return slug or "event"
