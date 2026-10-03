"""Renewals for a season: tools/rent.pl --holders sums each holder's plots; membership is added here."""
import subprocess
from pathlib import Path

from .money import pounds

MEMBERSHIP = 500
RENT_PL = Path(__file__).resolve().parent.parent / "tools" / "rent.pl"


def renewal_lines(plots_path, season):
    result = subprocess.run(["perl", str(RENT_PL), "--holders", "--season", str(season), str(plots_path)],
                            capture_output=True, text=True, check=True)
    lines = [f"Renewals for season {season}-{(season + 1) % 100:02d}, due by 31 October {season}"]
    due = n = n_plots = 0
    for row in result.stdout.splitlines()[1:]:
        holder, plots, rent, water = row.split("\t")
        if holder == "total":
            continue
        total = int(rent) + int(water) + MEMBERSHIP
        due += total
        n += 1
        n_plots += len(plots.split(", "))
        lines.append(f"{holder}: {plots}: rent {pounds(int(rent))}, water {pounds(int(water))}, "
                     f"membership {pounds(MEMBERSHIP)}, total {pounds(total)}")
    lines.append(f"{n} holder{'' if n == 1 else 's'}, {n_plots} plot{'' if n_plots == 1 else 's'}, "
                 f"total due {pounds(due)}")
    return lines
