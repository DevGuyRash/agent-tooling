"""Reference for revise-ssot-go: permitctl's three commands (quote, renewals, forecast) as the fixture prints
them, under a permit charge rule passed in, so the check can compute what each command should print under the
documented rule and after it edits one part of that rule.

RULE is docs/permit-charges.md for 2027/28: the request (band G over 255 g/km at 292.00, the diesel surcharge
45.00) and every earlier change, which the fixture's three copies of the rule each missed one of. A rule is a
dict: bands ([name, highest g/km or None for the top band, pence]), diesel (pence added for a diesel), extra
(pence added for later permits at an address), extra_from (the first permit at an address that pays extra: 2,
or 3 under the check's edit of how the parts combine), and exclusive (an edit of the rule's wording: a vehicle
exactly on a band's upper figure goes in the next band). Band labels come from the figures alone, as the
fixture computes them. The quote shows the later-permit line only when the surcharge applies, as the fixture
does; the renewal letters' ", second permit" note describes the permit (household_permit 2 or more), as the
fixture's does, and with notes="surcharge" it follows the surcharge instead. The two differ only when
extra_from is not 2, and the check accepts either there.

COPIES are the fixture's three copies of the rule as they would be with the request applied to each and nothing
else (quote.go's 50.00 for later permits, renewals.go's band C at 90.00, forecast.go's exclusive comparison):
the check uses them only to verify which hidden inputs the copies disagree on.

run(rule, argv, files) -> (exit status, stdout) or (exit status, None) for a refusal (1: an unreadable export,
`permitctl: ...` on stderr; 2: a bad command line). argv names files as {name}, looked up in files; a name not
in files is a missing file."""
import copy
import csv
import datetime as dt
import io
import re

RULE = {
    "bands": [["A", 100, 3200], ["B", 120, 5800], ["C", 150, 9600], ["D", 185, 14200], ["E", 225, 18800],
              ["F", 255, 23600], ["G", None, 29200]],
    "diesel": 4500,
    "extra": 6000,
    "extra_from": 2,
    "exclusive": False,
}
COMMANDS = ("quote", "renewals", "forecast")
NOTES = ("permit", "surcharge")
FUELS = ("petrol", "diesel", "hybrid", "electric")
COLUMNS = ("permit_id", "address", "vrm", "co2", "fuel", "household_permit", "expires")


def mutated(rule=RULE, pence=None, upto=None, **changes):
    """rule with some parts replaced: pence and upto as {band: value}, diesel, extra, extra_from, exclusive."""
    out = copy.deepcopy(rule)
    for b in out["bands"]:
        if pence and b[0] in pence:
            b[2] = pence[b[0]]
        if upto and b[0] in upto:
            b[1] = upto[b[0]]
    out.update(changes)
    return out


COPIES = {
    "quote.go": mutated(extra=5000),
    "renewals.go": mutated(pence={"C": 9000}),
    "forecast.go": mutated(exclusive=True),
}


class Refused(Exception):
    def __init__(self, rc):
        super().__init__(rc)
        self.rc = rc


def fmt(pence):
    return f"{pence // 100}.{pence % 100:02d}"


def band(rule, co2):
    """(name, label, pence) of the band a vehicle emitting co2 g/km is in."""
    lower = 0
    for name, upto, pence in rule["bands"]:
        inside = upto is None or (co2 < upto if rule["exclusive"] else co2 <= upto)
        if inside:
            if upto is None:
                label = f"over {lower - 1} g/km"
            elif lower == 0:
                label = f"up to {upto} g/km"
            else:
                label = f"{lower} to {upto} g/km"
            return name, label, pence
        lower = upto + 1
    raise AssertionError("the top band has no limit")


def later(rule, household):
    """Whether the household-th permit at an address pays the later-permit surcharge."""
    return household >= rule["extra_from"]


def charge(rule, co2, fuel, household):
    name, _, pence = band(rule, co2)
    return name, pence + (rule["diesel"] if fuel == "diesel" else 0) + (rule["extra"] if later(rule, household) else 0)


def _atoi(text):
    if not re.fullmatch(r"[+-]?\d+", text):
        raise ValueError(text)
    return int(text)


def _date(text):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(text)
    return dt.date.fromisoformat(text)


def permits(files, name):
    if name not in files:
        raise Refused(1)
    rows = list(csv.reader(io.StringIO(files[name], newline="")))
    if not rows:
        raise Refused(1)
    at = {h.removeprefix("\ufeff").strip(): i for i, h in enumerate(rows[0])}
    if any(c not in at for c in COLUMNS):
        raise Refused(1)
    out = []
    for rec in rows[1:]:
        if not rec:  # encoding/csv skips empty lines
            continue
        get = {c: (rec[at[c]].strip() if at[c] < len(rec) else "") for c in COLUMNS}
        try:
            co2, household = _atoi(get["co2"]), _atoi(get["household_permit"])
            expires = _date(get["expires"])
        except ValueError:
            raise Refused(1) from None
        fuel = get["fuel"].lower()
        if co2 < 0 or household < 1 or fuel not in FUELS:
            raise Refused(1)
        out.append({"id": get["permit_id"], "address": get["address"], "vrm": get["vrm"].upper(), "co2": co2,
                    "fuel": fuel, "household": household, "expires": expires})
    return out


def quote(rule, co2, fuel, household):
    name, label, pence = band(rule, co2)
    lines = [(f"Band {name} ({label})", pence)]
    if fuel == "diesel":
        lines.append(("Diesel surcharge", rule["diesel"]))
    if later(rule, household):
        lines.append(("Second permit at the address", rule["extra"]))
    return "".join(f"{l}: {fmt(p)}\n" for l, p in lines) + f"Total: {fmt(sum(p for _, p in lines))}\n"


def renewals(rule, all_permits, year, month, notes="permit"):
    label = f"{year:04d}-{month:02d}"
    due = sorted((p for p in all_permits if (p["expires"].year, p["expires"].month) == (year, month)),
                 key=lambda p: (p["expires"], p["id"]))
    if not due:
        return f"No renewals due in {label}.\n"
    out, total = [], 0
    for p in due:
        name, pence = charge(rule, p["co2"], p["fuel"], p["household"])
        second = later(rule, p["household"]) if notes == "surcharge" else p["household"] > 1
        note = (", diesel" if p["fuel"] == "diesel" else "") + (", second permit" if second else "")
        out.append(f"{p['id']} {p['vrm']} ({p['address']}): band {name}{note}, {fmt(pence)}\n")
        total += pence
    out.append(f"{len(due)} renewal{'' if len(due) == 1 else 's'} due in {label}, {fmt(total)} in total\n")
    return "".join(out)


def forecast(rule, all_permits):
    names = [b[0] for b in rule["bands"]]
    counts, income = dict.fromkeys(names, 0), dict.fromkeys(names, 0)
    for p in all_permits:
        name, pence = charge(rule, p["co2"], p["fuel"], p["household"])
        counts[name] += 1
        income[name] += pence
    rows = [f"{'band':<5} {'permits':>7} {'income':>10}\n"]
    rows += [f"{n:<5} {counts[n]:>7} {fmt(income[n]):>10}\n" for n in names]
    rows.append(f"{'total':<5} {sum(counts.values()):>7} {fmt(sum(income.values())):>10}\n")
    return "".join(rows)


def _file(arg):
    m = re.fullmatch(r"\{([\w.-]+)\}", arg)
    return m.group(1) if m else arg


def _flags(args, spec):
    """Go's flag package as the fixture uses it: -name value, --name value, -name=value, and -name for a bool
    flag, up to the first argument that is not a flag. ({name: value}, the rest) or Refused(2)."""
    values, i = {}, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if not a.startswith("-") or a == "-":
            break
        name, _, value = a.lstrip("-").partition("=")
        if name not in spec:
            raise Refused(2)
        if spec[name] is bool:
            values[name] = value.lower() in ("1", "t", "true") if "=" in a else True
            i += 1
            continue
        if "=" not in a:
            if i + 1 >= len(args):
                raise Refused(2)
            value = args[i + 1]
            i += 1
        if spec[name] is int:
            try:
                value = _atoi(value)
            except ValueError:
                raise Refused(2) from None
        values[name] = value
        i += 1
    return values, args[i:]


def run(rule, argv, files, notes="permit"):
    """(exit status, stdout or None) of `permitctl ARGV` under rule, the renewal notes in the style named."""
    try:
        if not argv or argv[0] not in COMMANDS:
            raise Refused(2)
        cmd, args = argv[0], argv[1:]
        if cmd == "quote":
            f, rest = _flags(args, {"co2": int, "fuel": str, "second": bool})
            co2, fuel = f.get("co2", -1), f.get("fuel", "petrol").lower()
            if rest or co2 < 0 or fuel not in FUELS:
                raise Refused(2)
            return 0, quote(rule, co2, fuel, 2 if f.get("second") else 1)
        if cmd == "renewals":
            f, rest = _flags(args, {"month": str})
            if len(rest) != 1 or not re.fullmatch(r"\d{4}-\d{2}", f.get("month", "")):
                raise Refused(2)
            year, month = map(int, f["month"].split("-"))
            if not 1 <= month <= 12:
                raise Refused(2)
            return 0, renewals(rule, permits(files, _file(rest[0])), year, month, notes)
        if len(args) != 1 or args[0].startswith("-"):
            raise Refused(2)
        return 0, forecast(rule, permits(files, _file(args[0])))
    except Refused as r:
        return r.rc, None
