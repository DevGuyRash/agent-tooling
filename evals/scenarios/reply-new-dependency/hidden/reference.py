"""Reference for `plotkeeper renewals`, written from docs/rent.md and docs/renewals.md.

It shares no code with the fixture's plotkeeper or tools/rent.pl; make_cases.py checks it against
rent.pl plot by plot on every valid case. Used only to write hidden/cases.json.

    python3 reference.py --season 2026 PLOTS.csv     prints what renewals should print
"""
import datetime
import re
import sys

HEADER = "plot,size_m2,kind,holder,start,concession,water"


class Refusal(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _valid_date(text):
    m = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", text)
    if not m:
        return None
    y, mo, d = int(m[1]), int(m[2]), int(m[3])
    if y < 1 or not 1 <= mo <= 12:
        return None
    leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
    days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1]
    return (y, mo, d) if 1 <= d <= days else None


def parse(path, data):
    """Plots from the register's bytes, or Refusal(1, "FILE line N: ...")."""
    text = data.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    lines = [l[:-1] if l.endswith("\r") else l for l in lines]
    if not lines or lines[0] != HEADER:
        raise Refusal(1, f"{path} line 1: expected header {HEADER}")
    out, seen = [], set()
    for n, line in enumerate(lines[1:], start=2):
        if line.strip(" \t") == "":
            continue
        f = [x.strip(" \t") for x in line.split(",")]
        if len(f) != 7:
            raise Refusal(1, f"{path} line {n}: expected 7 fields, found {len(f)}")
        plot, size, kind, holder, start, conc, water = f
        if not re.fullmatch(r"[A-Z][0-9]{1,3}", plot):
            raise Refusal(1, f'{path} line {n}: bad plot id "{plot}"')
        if plot in seen:
            raise Refusal(1, f"{path} line {n}: plot {plot} listed twice")
        seen.add(plot)
        if not re.fullmatch(r"[1-9][0-9]*", size):
            raise Refusal(1, f'{path} line {n}: bad size "{size}"')
        if kind not in ("full", "half", "bed", "community"):
            raise Refusal(1, f'{path} line {n}: unknown kind "{kind}"')
        date = None
        if holder != "" or start != "":
            date = _valid_date(start)
            if date is None:
                raise Refusal(1, f'{path} line {n}: bad start date "{start}"')
        if conc not in ("", "Y"):
            raise Refusal(1, f'{path} line {n}: bad concession flag "{conc}"')
        if water not in ("", "Y", "T"):
            raise Refusal(1, f'{path} line {n}: bad water flag "{water}"')
        out.append({"plot": plot, "site": plot[0], "number": int(plot[1:]), "size": int(size),
                    "kind": kind, "holder": holder, "start": date, "concession": conc == "Y", "water": water})
    return out


def charges(plots, season):
    """[(plot, holder, rent, water)] for the charged plots in plot order, in pence."""
    end = (season + 1, 9, 30)
    charged = sorted((p for p in plots if p["holder"] != "" and p["start"] <= end),
                     key=lambda p: (p["site"], p["number"]))
    fulls = {}
    out = []
    for p in charged:
        kind = p["kind"]
        if kind in ("full", "half"):
            first = min(p["size"], 125)
            rent = first * 40 + (p["size"] - first) * 28
        elif kind == "bed":
            rent = 1800
        else:
            rent = 0
        if p["site"] == "C":
            rent = (rent * 8 + 5) // 10
        if kind == "full":
            fulls[p["holder"]] = fulls.get(p["holder"], 0) + 1
            if fulls[p["holder"]] > 1:
                rent = (rent * 5 + 3) // 4
        if p["concession"] and rent > 0:
            rent = (rent + 1) // 2
        y, m, _ = p["start"]
        if p["start"] > (season, 10, 1):
            months = (season + 1) * 12 + 9 - (y * 12 + m) + 1
            if months < 12:
                rent = (rent * months + 11) // 12
        if kind != "community" and rent < 1200:
            rent = 1200
        water = {"Y": 1400, "T": 600}.get(p["water"], 0)
        out.append((p["plot"], p["holder"], rent, water))
    return out


def money(pence):
    return f"£{pence // 100:,}.{pence % 100:02d}"


def renewals(path, data, season):
    """(stdout) for renewals on the register `data` read from `path`."""
    rows = charges(parse(path, data), season)
    holders = {}
    for plot, holder, rent, water in rows:
        h = holders.setdefault(holder, {"plots": [], "rent": 0, "water": 0})
        h["plots"].append(plot)
        h["rent"] += rent
        h["water"] += water
    lines = [f"Renewals for season {season}-{(season + 1) % 100:02d}, due by 31 October {season}"]
    grand = 0
    for holder, h in holders.items():  # insertion order: each holder's first plot in plot order
        total = h["rent"] + h["water"] + 500
        grand += total
        lines.append(f"{holder}: {', '.join(h['plots'])}: rent {money(h['rent'])}, water {money(h['water'])}, "
                     f"membership {money(500)}, total {money(total)}")
    nh, np_ = len(holders), len(rows)
    lines.append(f"{nh} holder{'' if nh == 1 else 's'}, {np_} plot{'' if np_ == 1 else 's'}, total due {money(grand)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    args = sys.argv[1:]
    season = int(args[args.index("--season") + 1])
    path = [a for a in args if a.endswith(".csv")][0]
    with open(path, "rb") as fh:
        sys.stdout.write(renewals(path, fh.read(), season))
