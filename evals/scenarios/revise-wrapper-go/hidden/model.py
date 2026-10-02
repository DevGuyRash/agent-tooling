"""ferry punctuality as docs/punctuality.md describes it, written for make_cases.py: with Variant() it must agree
with the fixture's ferry on every hidden case, and each careless port in VARIANTS must disagree on at least one, so
the hidden cases are known to tell those ports apart. Go's own unstable sorts (sort.Slice, slices.SortFunc) are
checked by a qualify arm instead, since their tie order is Go's. Not used by the check."""
import math
from dataclasses import dataclass

DIR = "{dir}/"


@dataclass(frozen=True)
class Variant:
    name: str = "as documented"
    bands: str = "floor"         # "truncate": Go's integer division, so 1 to 4 minutes early lands in band 0
    median: str = "halfway"      # "truncate": integer (a+b)/2
    nothing_ran: str = "first"   # "last": a route where nothing ran sorts after the others; "zero": its share is 0
    share: str = "exact"         # "percent": whole percent, truncated (on*100/ran); "percent-rounded": rounded
    order: str = "seen"          # "name": routes ordered by name before sorting
    ties: str = "seen"           # "reversed": equal shares in reverse first-seen order
    on_time: str = "at-most-5"   # "under-5": 5 minutes late is late
    early: str = "on-time"       # "late": an early departure is not on time


VARIANTS = [
    Variant(name="bands by truncating division", bands="truncate"),
    Variant(name="median truncated", median="truncate"),
    Variant(name="nothing-ran routes last", nothing_ran="last"),
    Variant(name="nothing ran as a share of 0", nothing_ran="zero"),
    Variant(name="whole-percent shares", share="percent"),
    Variant(name="rounded whole-percent shares", share="percent-rounded"),
    Variant(name="routes by name", order="name"),
    Variant(name="ties reversed", ties="reversed"),
    Variant(name="5 minutes late is late", on_time="under-5"),
    Variant(name="early departures not on time", early="late"),
]


def minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def delay(sched, dep):
    d = minutes(dep) - minutes(sched)
    return d + 1440 if d < -720 else d - 1440 if d > 720 else d


def parse_args(args):
    frm = to = None
    logs, i = [], 0
    while i < len(args):
        if args[i] in ("--from", "--to"):
            frm, to = (args[i + 1], to) if args[i] == "--from" else (frm, args[i + 1])
            i += 2
        else:
            logs.append(args[i][len(DIR):] if args[i].startswith(DIR) else args[i])
            i += 1
    return frm, to, logs


def output_for(case, v):
    frm, to, logs = parse_args(case["args"][1:])
    delays = {}
    for name in logs:
        for line in case["files"][name].splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            date, route, sched, dep = line.split("\t")
            if (frm and date < frm) or (to and date > to):
                continue
            delays.setdefault(route, []).append(None if dep == "cancelled" else delay(sched, dep))
    if not delays:
        return "no sailings\n"
    names = sorted(delays) if v.order == "name" else list(delays)
    routes = []
    for route in names:
        ds = delays[route]
        ran = [d for d in ds if d is not None]
        bands = {}
        for d in ran:
            start = (d // 5 if v.bands == "floor" else int(d / 5)) * 5
            bands[start] = bands.get(start, 0) + 1
        limit = 5 if v.on_time == "at-most-5" else 4
        on_time = sum(1 for d in ran if d <= limit and (v.early == "on-time" or d >= 0))
        s = sorted(ran)
        n = len(s)
        if not n:
            median = "-"
        elif n % 2:
            median = str(s[n // 2])
        elif v.median == "truncate":
            median = str(int((s[n // 2 - 1] + s[n // 2]) / 2))
        else:
            total = s[n // 2 - 1] + s[n // 2]
            median = str(total // 2) if total % 2 == 0 else f"{total / 2:.1f}"
        routes.append({"route": route, "sailings": len(ds), "cancelled": len(ds) - n, "on_time": on_time,
                       "median": median, "worst": str(max(ran)) if ran else "-",
                       "bands": " ".join(f"{k}:{c}" for k, c in sorted(bands.items())) or "-"})

    def key(r):
        ran = r["sailings"] - r["cancelled"]
        if not ran:
            return {"first": -1, "last": math.inf, "zero": 0}[v.nothing_ran]
        if v.share == "percent":
            return r["on_time"] * 100 // ran
        if v.share == "percent-rounded":
            return math.floor(r["on_time"] * 100 / ran + 0.5)  # Go's math.Round for a positive share
        return r["on_time"] / ran

    if v.ties == "reversed":
        routes = sorted(reversed(routes), key=key)
    else:
        routes.sort(key=key)
    header = ["route", "sailings", "cancelled", "on time", "median", "worst", "by 5 minutes"]
    rows = [[r["route"], str(r["sailings"]), str(r["cancelled"]), str(r["on_time"]), r["median"], r["worst"], r["bands"]]
            for r in routes]
    table = [header, *rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(header) - 1)]
    lines = []
    for row in table:
        cells = [c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(row, widths))]
        lines.append("  ".join([*cells, row[-1]]))
    total = sum(r["sailings"] for r in routes)
    cancelled = sum(r["cancelled"] for r in routes)
    on = sum(r["on_time"] for r in routes)
    return "\n".join(lines) + f"\n\n{total} sailings, {cancelled} cancelled, {on} of {total - cancelled} on time\n"
