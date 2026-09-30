class DuplicateOrderError(Exception):
    """Raised when the same order_id appears twice in a batch."""


class OrderBatch:
    """Accepts rows one at a time, rejecting a repeated order_id."""

    def __init__(self):
        self._seen = set()
        self.accepted = []

    def add(self, row):
        order_id = row["order_id"]
        if order_id in self._seen:
            raise DuplicateOrderError(order_id)
        self._seen.add(order_id)
        self.accepted.append(row)


def import_rows(rows):
    """Import a batch of rows, raising DuplicateOrderError on the first repeated order_id."""
    batch = OrderBatch()
    for row in rows:
        batch.add(row)
    return batch.accepted
