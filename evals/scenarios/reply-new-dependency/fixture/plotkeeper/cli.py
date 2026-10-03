"""plotkeeper's command line: python3 -m plotkeeper COMMAND ..."""
import argparse
import sys

from .plots import WATER_NAMES, PlotsError, plot_order, read_plots
from .waiting import WaitingError, read_waiting

DEFAULT_PLOTS = "data/plots.csv"
DEFAULT_WAITING = "data/waiting.csv"


def cmd_plots(args):
    plots = sorted(read_plots(args.plots), key=plot_order)
    if args.vacant:
        plots = [p for p in plots if p.vacant]
    rows = [("Plot", "Size", "Kind", "Holder", "Since", "Water")]
    for p in plots:
        rows.append((p.plot, f"{p.size_m2} m2", p.kind, p.holder or "(vacant)",
                     p.start.isoformat() if p.start else "-", WATER_NAMES[p.water]))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip())
    return 0


def cmd_waiting(args):
    people = read_waiting(args.file)
    if not people:
        print("Nobody is waiting.")
        return 0
    for i, w in enumerate(people, start=1):
        print(f"{i:>3}. {w.name} (since {w.joined.isoformat()}, wants {w.wants})")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="plotkeeper", description="Hollins Lane Allotment Society records.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plots", help="list the plots in the register")
    p.add_argument("--plots", default=DEFAULT_PLOTS, help=f"plot register (default {DEFAULT_PLOTS})")
    p.add_argument("--vacant", action="store_true", help="only vacant plots")
    p.set_defaults(func=cmd_plots)

    w = sub.add_parser("waiting", help="show the waiting list, longest-waiting first")
    w.add_argument("--file", default=DEFAULT_WAITING, help=f"waiting list (default {DEFAULT_WAITING})")
    w.set_defaults(func=cmd_waiting)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (PlotsError, WaitingError) as exc:
        print(f"plotkeeper: {exc}", file=sys.stderr)
        return 1
