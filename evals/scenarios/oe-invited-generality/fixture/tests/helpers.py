import csv
import os
import tempfile

HEADER = ["week", "item", "category", "units", "price_cents"]


def data_dir(rows, ini=None):
    """A temporary data directory holding sales.csv with `rows` (lists in HEADER order)."""
    path = tempfile.mkdtemp()
    with open(os.path.join(path, "sales.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    if ini is not None:
        with open(os.path.join(path, "stallbook.ini"), "w", encoding="utf-8") as handle:
            handle.write(ini)
    return path
