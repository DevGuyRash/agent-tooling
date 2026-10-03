"""shiftboard's command line."""
import argparse
import sys

from . import board, roster, text


def _check(shifts):
    if not shifts:
        return "no shifts"
    days = sorted(s.date for s in shifts)
    return f"{len(shifts)} shifts from {days[0]} to {days[-1]}"


def _hours(shifts):
    totals = {}
    for s in shifts:
        count, hours = totals.get(s.volunteer, (0, 0.0))
        totals[s.volunteer] = (count + 1, hours + s.hours)
    order = sorted(totals.items(), key=lambda item: (-item[1][1], item[0]))
    rows = [(name, str(count), f"{hours:.1f}") for name, (count, hours) in order]
    return "\n".join(text.table(["Volunteer", "Shifts", "Hours"], rows))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shiftboard", description="Rota tools for the Northgate Community Kitchen.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="check that a roster reads cleanly").add_argument("roster")
    commands.add_parser("hours", help="hours per volunteer").add_argument("roster")
    week = commands.add_parser("week", help="the week board for the kiosk")
    week.add_argument("roster")
    week.add_argument("week")
    args = parser.parse_args(argv)

    if args.command == "week":
        try:
            board.parse_week(args.week)
        except ValueError:
            print(f"shiftboard: bad week '{args.week}'", file=sys.stderr)
            return 2

    try:
        shifts = roster.load(args.roster)
    except roster.RosterError as err:
        print(f"shiftboard: {err}", file=sys.stderr)
        return 1
    except OSError as err:
        print(f"shiftboard: cannot read {args.roster}: {err.strerror}", file=sys.stderr)
        return 1

    if args.command == "check":
        print(_check(shifts))
    elif args.command == "hours":
        print(_hours(shifts))
    elif args.command == "week":
        print(board.render_week(shifts, args.week))
    return 0
