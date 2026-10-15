"""The cards file and card lookups (SPEC R4)."""
import csv
from collections import namedtuple

Card = namedtuple("Card", "id name stamps")


class Directory:
    """Finds cards through `lookup(card_id)`, which returns a Card or None."""

    def __init__(self, lookup):
        self._lookup = lookup

    def get(self, card_id):
        """The Card with this id; KeyError when the cards file has none."""
        card = self._lookup(card_id)
        if card is None:
            raise KeyError(card_id)
        return card


def file_lookup(path):
    """A lookup function over the cards CSV at `path` (header `id,name,stamps`)."""

    def lookup(card_id):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["id"] == card_id:
                    return Card(row["id"], row["name"], int(row["stamps"]))
        return None

    return lookup
