"""Compare plotkeeper's per-plot rent and water with Dev's tools/rent.pl, for whoever has perl installed.

    python3 scripts/compare_with_rent_pl.py --season 2026 [data/plots.csv]

Prints every plot where the two disagree and exits 1 if any do. plotkeeper itself never runs rent.pl; this
is only a cross-check for when the rules in docs/rent.md change.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plotkeeper.plots import read_plots  # noqa: E402
from plotkeeper.renewals import plot_charges  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("plots", nargs="?", default="data/plots.csv")
    args = parser.parse_args()
    out = subprocess.run(["perl", "tools/rent.pl", "--season", str(args.season), args.plots],
                         capture_output=True, text=True, check=True).stdout
    theirs = {}
    for line in out.splitlines()[1:]:
        plot, _holder, rent, water = line.split("\t")
        if plot != "total":
            theirs[plot] = (int(rent), int(water))
    ours = {p.plot: (rent, water) for p, rent, water in plot_charges(read_plots(args.plots), args.season)}
    differ = sorted(set(theirs) | set(ours))
    bad = [plot for plot in differ if theirs.get(plot) != ours.get(plot)]
    for plot in bad:
        print(f"{plot}: rent.pl {theirs.get(plot)}, plotkeeper {ours.get(plot)}")
    print(f"{len(differ) - len(bad)} of {len(differ)} plots agree")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
