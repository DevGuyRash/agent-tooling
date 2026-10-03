"""Renewals for a season: rent and water per plot (docs/rent.md), plus membership per holder."""
import datetime

from .money import pounds
from .plots import plot_order

MEMBERSHIP = 500
WATER = {"": 0, "Y": 1400, "T": 600}


def _months_due(start, season):
    """Whole months from the month the holder joined to September, out of 12."""
    if start <= datetime.date(season, 10, 1):
        return 12
    return (season + 1) * 12 + 9 - (start.year * 12 + start.month) + 1


def plot_charges(plots, season):
    """[(plot, rent, water)] in pence for every charged plot, in plot order."""
    end = datetime.date(season + 1, 9, 30)
    charged = sorted((p for p in plots if not p.vacant and p.start <= end), key=plot_order)
    full_plots = {}
    out = []
    for p in charged:
        if p.kind in ("full", "half"):
            first = min(p.size_m2, 125)
            rent = first * 40 + (p.size_m2 - first) * 28
        elif p.kind == "bed":
            rent = 1800
        else:
            rent = 0
        if p.site == "C":
            rent = (rent * 8 + 5) // 10
        if p.kind == "full":
            full_plots[p.holder] = full_plots.get(p.holder, 0) + 1
            if full_plots[p.holder] > 1:
                rent = (rent * 5 + 3) // 4
        if p.concession and rent > 0:
            rent = (rent + 1) // 2
        months = _months_due(p.start, season)
        if months < 12:
            rent = rent * months // 12
        if p.kind != "community" and rent < 1200:
            rent = 1200
        out.append((p, rent, WATER[p.water]))
    return out


def renewal_lines(plots, season):
    holders = {}
    for p, rent, water in plot_charges(plots, season):
        h = holders.setdefault(p.holder, {"plots": [], "rent": 0, "water": 0})
        h["plots"].append(p.plot)
        h["rent"] += rent
        h["water"] += water
    lines = [f"Renewals for season {season}-{(season + 1) % 100:02d}, due by 31 October {season}"]
    due = 0
    n_plots = 0
    for holder, h in holders.items():
        total = h["rent"] + h["water"] + MEMBERSHIP
        due += total
        n_plots += len(h["plots"])
        lines.append(f"{holder}: {', '.join(h['plots'])}: rent {pounds(h['rent'])}, water {pounds(h['water'])}, "
                     f"membership {pounds(MEMBERSHIP)}, total {pounds(total)}")
    n = len(holders)
    lines.append(f"{n} holder{'' if n == 1 else 's'}, {n_plots} plot{'' if n_plots == 1 else 's'}, "
                 f"total due {pounds(due)}")
    return lines
