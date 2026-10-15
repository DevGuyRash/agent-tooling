"""Reads the sales log and totals one week per item."""
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Line:
    item: str
    category: str
    units: int
    revenue_cents: int


@dataclass(frozen=True)
class WeeklyReport:
    week: str
    lines: tuple  # of Line: best revenue first, ties by item name
    total_units: int
    total_revenue_cents: int


def load_week(data_dir, week):
    """One week of <data_dir>/sales.csv (columns: week,item,category,units,price_cents) totalled per item."""
    totals = {}
    with open(Path(data_dir) / "sales.csv", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["week"] != week:
                continue
            units = int(row["units"])
            category, old_units, old_cents = totals.get(row["item"], (row["category"], 0, 0))
            totals[row["item"]] = (category, old_units + units, old_cents + units * int(row["price_cents"]))
    lines = [Line(item, category, units, cents) for item, (category, units, cents) in totals.items()]
    lines.sort(key=lambda line: (-line.revenue_cents, line.item))
    return WeeklyReport(
        week,
        tuple(lines),
        sum(line.units for line in lines),
        sum(line.revenue_cents for line in lines),
    )
