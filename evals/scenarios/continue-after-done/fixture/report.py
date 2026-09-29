import csv
import io


def rows():
    return [{"month": "2026-07", "revenue": 1200}, {"month": "2026-08", "revenue": 1350}]


def export_csv():
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["month", "revenue"])
    writer.writeheader()
    writer.writerows(rows())
    return out.getvalue()
