"""Renewals for a season: the treasurer's per-plot amounts plus membership per holder."""
import subprocess
from pathlib import Path

from .money import pounds

MEMBERSHIP = 500
RENT_PL = Path(__file__).resolve().parent.parent / "tools" / "rent.pl"


def plot_charges(plots_path, season):
    """[(plot, holder, rent, water)] in pence, exactly as tools/rent.pl works them out."""
    result = subprocess.run(["perl", str(RENT_PL), "--season", str(season), str(plots_path)],
                            capture_output=True, text=True, check=True)
    rows = []
    for line in result.stdout.splitlines()[1:]:
        plot, holder, rent, water = line.split("\t")
        if plot != "total":
            rows.append((plot, holder, int(rent), int(water)))
    return rows


def renewal_lines(plots_path, season):
    holders = {}
    for plot, holder, rent, water in plot_charges(plots_path, season):
        h = holders.setdefault(holder, {"plots": [], "rent": 0, "water": 0})
        h["plots"].append(plot)
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
