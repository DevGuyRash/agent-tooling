"""Call numbers in the library's house scheme (docs/callnumbers.md): reading, checking, and shelf order.

    >>> cn = parse("  j 595.789 kir 2021 ")
    >>> str(cn), cn.section()
    ('J 595.789 KIR 2021', "Children's · 500s")
    >>> sorted(["641.59 HAZ", "641.5945 HAZ", "641.5 A2"], key=lambda t: parse(t).sort_key())
    ['641.5 A2', '641.59 HAZ', '641.5945 HAZ']
"""
import re
from dataclasses import dataclass

# Collection prefixes, in the order the collections are shelved; no prefix is the adult collection.
COLLECTIONS = {"": (0, "Adult"), "J": (1, "Children's"), "YA": (2, "Young adult"), "REF": (3, "Reference"),
               "OS": (4, "Oversize")}
# Word classes, shelved after every Dewey number of their collection, in this order.
WORD_CLASSES = {"B": (1, "Biography"), "GN": (2, "Graphic novels"), "FIC": (3, "Fiction")}
DEWEY = re.compile(r"(\d{3})(?:\.(\d+))?")
CUTTER = re.compile(r"([A-Z]{1,3})(\d*)")
NAME = re.compile(r"[A-Z][A-Z'-]*")
YEAR = re.compile(r"(?:1[5-9]|20)\d\d")
VOLUME = re.compile(r"V\.([1-9]\d{0,2})")
COPY = re.compile(r"C\.([1-9]\d{0,2})")


class CallNumberError(ValueError):
    """A call number that does not follow the scheme; the message says what is wrong."""


@dataclass(frozen=True)
class CallNumber:
    collection: str  # "" (adult), "J", "YA", "REF", or "OS"
    klass: str  # a Dewey number as written ("641.5945") or a word class ("FIC")
    mark: str  # the Cutter (Dewey) or the name (word classes), as written
    year: int | None = None
    volume: int | None = None
    copy: int | None = None

    def __str__(self):
        parts = [self.collection, self.klass, self.mark, str(self.year or ""),
                 f"V.{self.volume}" if self.volume else "", f"C.{self.copy}" if self.copy else ""]
        return " ".join(p for p in parts if p)

    def sort_key(self):
        """Shelf order: collection, then Dewey numbers before the word classes, then the class, the mark, the year
        (none first), the volume, and the copy. Dewey fractions and Cutter digits compare as decimal fractions."""
        if self.klass in WORD_CLASSES:
            kind, whole, fraction = WORD_CLASSES[self.klass][0], 0, ""
            mark = (re.sub(r"['-]", "", self.mark), "")
        else:
            m = DEWEY.fullmatch(self.klass)
            kind, whole, fraction = 0, int(m.group(1)), (m.group(2) or "").rstrip("0")
            c = CUTTER.fullmatch(self.mark)
            mark = (c.group(1), c.group(2).rstrip("0"))
        return (COLLECTIONS[self.collection][0], kind, whole, fraction, mark, self.year or 0, self.volume or 0,
                self.copy or 0)

    def section(self):
        """The heading a shelf list groups this call number under: its collection and its hundreds or word class."""
        name = WORD_CLASSES[self.klass][1] if self.klass in WORD_CLASSES else f"{self.klass[0]}00s"
        return f"{COLLECTIONS[self.collection][1]} · {name}"


def normalize(text):
    """Upper case, surrounding space removed, and every run of white space made one space."""
    return " ".join(text.upper().split())


def parse(text):
    """The CallNumber that text (in any case and spacing) writes, or CallNumberError."""
    words = normalize(text).split(" ") if normalize(text) else []
    if not words:
        raise CallNumberError("no call number")
    collection = ""
    if words[0] in COLLECTIONS and words[0]:
        collection = words.pop(0)
        if not words:
            raise CallNumberError(f"no class after '{collection}'")
    klass = words.pop(0)
    if klass[0].isdigit():
        if not DEWEY.fullmatch(klass):
            raise CallNumberError(f"bad class number '{klass}'")
        what, pattern = "cutter", CUTTER
    elif klass in WORD_CLASSES:
        what, pattern = "name", NAME
    else:
        raise CallNumberError(f"unknown class '{klass}'")
    if not words:
        raise CallNumberError(f"no {what} after '{klass}'")
    mark = words.pop(0)
    if not pattern.fullmatch(mark):
        raise CallNumberError(f"bad {what} '{mark}'")
    year = volume = copy = None
    stage = 0
    for word in words:
        if stage < 1 and YEAR.fullmatch(word):
            year, stage = int(word), 1
        elif stage < 2 and (m := VOLUME.fullmatch(word)):
            volume, stage = int(m.group(1)), 2
        elif stage < 3 and (m := COPY.fullmatch(word)):
            copy, stage = int(m.group(1)), 3
        else:
            raise CallNumberError(f"unexpected '{word}'")
    return CallNumber(collection, klass, mark, year, volume, copy)
