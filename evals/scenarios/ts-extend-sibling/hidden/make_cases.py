"""Regenerate the hidden inputs and expected results for ts-extend-sibling.

Run from anywhere: python3 hidden/make_cases.py. It writes data/*, cases.json, and expected/*.out next to itself.
Everything is deterministic: rebuilding gives the same bytes.

Expected results for `hours invoice` come from hidden/reference.py, which follows the fixture's docs/invoice.md.
Expected results for the existing commands (check, report) come from the fixture's own hours, run here with the
host's Node inside bubblewrap with the code and the data at the same paths the check uses, so file names in their
output match. The docs example case runs the command docs/invoice.md shows on copies of the fixture's rates.txt and
September timesheets, and the script checks that the document's example output is what the reference prints.

Most cases name their files by absolute paths under the check's data directory, outside the repository. The repo-*
cases read the repository's own rate card and September timesheets where they are, as people run the command: the
docs example exactly as written, relative to the repository root (the working directory in every root), and the
same files by absolute paths into the repository. Their "repo_files" are the fixture files the check puts into its
copy of the repository before running them, so what the agent did to those files does not matter.

The script also checks that money done in binary floating point gets cases wrong, whichever common way the
arithmetic is written (floats in currency units, or whole cents with a float on the way), and that whole cents with
an exact product get none wrong. Amounts go wrong in floats only on some of the amounts that land exactly on half a
cent, and which ones depends on how the arithmetic is written, so two clients' entries are chosen by a search over
ordinary rates and times rather than picked by hand (see tie_entries).
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
DATA = HERE / "data"
EXPECTED = HERE / "expected"
MOUNT = "/tmp/case"
DATA_AT = f"{MOUNT}/data"
CODE_AT = f"{MOUNT}/code"
sys.path.insert(0, str(HERE))
import reference  # noqa: E402

FILES = {}


def put(name, text):
    FILES[name] = text


# ---------------------------------------------------------------- money in floats
#
# How a careless port computes money, for the tie search below and the checks at the end. "units" ports keep money
# as floats in currency units: each amount is fn(m, c) with the rate parsed as a float (c / 100), put through
# Math.round(x * 100) / 100, the amounts summed as floats, the tax computed from that float subtotal, everything
# printed with toFixed(2). "cents" ports keep whole cents but let a float in on the way: each amount and the tax put
# through Math.round and summed exactly. m is an entry's or project's billed minutes, c the hourly rate in cents, s
# the subtotal (currency units for units ports, cents for cents ports), t the tax in hundredths of a percent. (Whole
# cents with the tax as Math.round(s * (t / 10000)) is left out: at ordinary tax rates and subtotals it is right.)


def js_round(x):
    """Math.round(x) for x >= 0."""
    f = math.floor(x)
    return f + 1 if x - f >= 0.5 else f


UNITS_AMOUNTS = {
    "m / 60 * r": lambda m, c: m / 60 * (c / 100),
    "m * r / 60": lambda m, c: m * (c / 100) / 60,
    "m * r * 100 / 60 / 100": lambda m, c: m * (c / 100) * 100 / 60 / 100,
}
UNITS_TAXES = {
    "s * p / 100": lambda s, t: s * (t / 100) / 100,
    "s * (p / 100)": lambda s, t: s * ((t / 100) / 100),
}
CENTS_AMOUNTS = {
    "Math.round(m / 60 * c)": lambda m, c: js_round(m / 60 * c),
    "Math.round(m * (c / 60))": lambda m, c: js_round(m * (c / 60)),
}
# Whole cents and Math.round on an exact quotient (the product stays an exact integer and an exact half is
# representable): right everywhere, so no hidden case may fail it.
EXACT_AMOUNT = lambda m, c: js_round(m * c / 60)  # noqa: E731
EXACT_TAX = lambda s, t: js_round(s * t / 10000)  # noqa: E731
EXACT_UNITS_AMOUNT = lambda m, c: reference.half_up(m * c, 60) / 100  # noqa: E731


def entry_wrong(kind, fn, m, c):
    """Whether a careless amount formula rounds one project's amount (m minutes at c cents an hour) wrongly."""
    exact = reference.half_up(m * c, 60)
    return (js_round(fn(m, c) * 100) if kind == "units" else fn(m, c)) != exact


# ---------------------------------------------------------------- amounts on exactly half a cent
#
# Two clients (quill and sable in card.txt, their time in ties.txt) bill one entry per project, each at the
# project's own rate, with increment 1 and no minimum, so a project's amount is that entry's minutes times its rate.
# Every entry's exact amount lands on half a cent. For each careless amount formula above, a search over ordinary
# rates and times, in a fixed shuffled order, takes the first two such entries the formula rounds the wrong way, one
# for each client; then a spread of other half-cent entries follows, so a formula not modeled here meets a variety
# of them too.

TIE_RATES = range(10_00, 300_00 + 1, 5)  # 10.00 to 300.00 an hour, in 5-cent steps
TIE_MINUTES = range(5, 8 * 60 + 1)       # 5 minutes to 8 hours
TIE_SPREAD = 8                           # other half-cent entries per client
TIE_PROJECTS = ["atlas", "banner", "brief", "catalog", "copy", "deck", "emails", "fonts", "gallery", "guide",
                "icons", "kiosk", "labels", "launch", "map", "menu", "motion", "packaging", "photos", "poster",
                "print", "signage", "social", "stickers", "survey", "video", "wiki", "zine"]


def tie_entries():
    """([(rate cents, minutes)] for quill, the same for sable)."""
    ties = [(c, m) for c in TIE_RATES for m in TIE_MINUTES if c * m % 60 == 30]
    random.Random(7).shuffle(ties)
    picked, used = ([], []), set()
    formulas = [("units", f) for f in UNITS_AMOUNTS.values()] + [("cents", f) for f in CENTS_AMOUNTS.values()]
    for kind, fn in formulas:
        found = []
        for c, m in ties:
            if (c, m) not in used and entry_wrong(kind, fn, m, c):
                found.append((c, m))
                if len(found) == 2:
                    break
        assert len(found) == 2, "a careless amount formula is never wrong on these rates and times"
        for side, tie in zip(picked, found):
            side.append(tie)
            used.add(tie)
    rest = [t for t in ties if t not in used][:2 * TIE_SPREAD]
    for i, tie in enumerate(rest):
        picked[i % 2].append(tie)
    return picked


def money_text(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def time_text(minutes, i):
    """An entry's TIME, in each of the ways timesheets.md allows, by turns."""
    if i % 3 == 0 and minutes <= 8 * 60:
        start = 9 * 60
        return f"{start // 60:02d}:{start % 60:02d}-{(start + minutes) // 60:02d}:{(start + minutes) % 60:02d}"
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes // 60}h{minutes % 60:02d}"


def tie_files():
    """(the card text for quill and sable, ties.txt)."""
    quill, sable = tie_entries()
    card, sheet = [], ["# December 2026: every entry here comes to exactly half a cent"]
    names = iter(TIE_PROJECTS)
    for client, header, entries in (
            ("quill", ["name = Quill & Ink Ltd", "currency = GBP", "rate = 85"], quill),
            ("sable", ["name = Sable Works", "currency = EUR", "rate = 100", "tax = 21"], sable)):
        card += ["", f"[{client}]", *header]
        for i, (c, m) in enumerate(entries):
            project = next(names)
            card.append(f"rate.{project} = {money_text(c)}")
            sheet.append(f"2026-12-{i % 20 + 1:02d}  {time_text(m, i)}  {client}/{project}  {project} work")
    return "\n".join(card) + "\n", "\n".join(sheet) + "\n"


TIE_CARD, TIE_SHEET = tie_files()


# ---------------------------------------------------------------- rate cards

put("card.txt", """\
# Rate card for the hidden cases.
   # an indented comment

[acme]
name = Acme Outdoor GmbH
currency = EUR
rate = 120
rate.site = 118.50
rate.brand = 140
rate.2d-anim = 99.99
increment = 15
minimum = 30
tax = 19

[bolt]
currency=GBP
name=Bolt Labs Ltd
rate=95.5
increment=6
tax=20

[north]
name = North Ferry Co.
currency = NOK
rate = 80.05

[fjord]
\tname\t=\tFjord Hotels AG
\tcurrency\t=\tCHF
\trate\t=\t150
\tincrement\t=\t10
\tminimum\t=\t45
\ttax\t=\t7.7

[kite]
name = Kite & Sons = Design #2
currency = USD
rate = 62.25
rate.ads = 64.10
increment = 5
tax = 8.25

[lumen]
name = Lumen Trust (pro bono)
currency = EUR
rate = 0
tax = 21

[moss]
name = Moss Bank AB
currency = SEK
rate = 1150
rate.app-2 = 1325.5
increment = 60
minimum = 120
tax = 25.00

# Half cents everywhere: amounts and taxes that land exactly on half a cent.
[tern]
name = Tern Studio
currency = EUR
rate = 12.35
tax = 19

[wren]
name = Wren & Co
currency = EUR
rate = 30
tax = 19

[yarrow]
name = Yarrow Labs
currency = CHF
rate = 60
tax = 7.7

# Every project of these two has one entry that comes to exactly half a cent.""" + TIE_CARD)

# One mistake each, after a good client so the line is not 1. (file, line of the mistake)
RATE_ERRORS = {
    "rates-unknown-key.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n\n[bad]\nname = Bad\ncurrency = EUR\nrate = 10\nrat = 12\n", 10),
    "rates-before-client.txt": ("# rates\n\nname = Floating\n[ok]\nname = OK\ncurrency = EUR\nrate = 10\n", 3),
    "rates-repeated-key.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\nincrement = 15\nminimum = 30\nincrement = 6\n", 7),
    "rates-repeated-project.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\nrate.site = 12\nrate.app = 9\nrate.site = 13\n", 7),
    "rates-repeated-client.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n[two]\nname = Two\ncurrency = EUR\nrate = 1\n[ok]\nname = Again\ncurrency = EUR\nrate = 10\n", 9),
    "rates-bad-rate.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n[bad]\nname = Bad\ncurrency = EUR\nrate = 12.345\n", 8),
    "rates-bad-project-rate.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\nrate.site = 9,50\n", 5),
    "rates-bad-currency.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n[bad]\nname = Bad\ncurrency = eur\nrate = 12\n", 7),
    "rates-zero-increment.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\nincrement = 0\n", 5),
    "rates-fraction-minimum.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\nminimum = 7.5\n", 5),
    "rates-high-tax.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\ntax = 100.5\n", 5),
    "rates-empty-name.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n[bad]\nname =\ncurrency = EUR\nrate = 1\n", 6),
    "rates-missing-rate.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n\n[bad]\nname = Bad\ncurrency = EUR\nincrement = 15\n\n[later]\nname = Later\ncurrency = EUR\nrate = 3\n", 6),
    "rates-missing-currency-last.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n\n[bad]\nname = Bad\nrate = 12\n", 6),
    "rates-not-a-setting.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\nincrement 15\n", 5),
    "rates-bad-header.txt": ("[ok]\nname = OK\ncurrency = EUR\nrate = 10\n[Bad Client]\nname = Bad\ncurrency = EUR\nrate = 1\n", 5),
}
for name, (text, _) in RATE_ERRORS.items():
    put(name, text)

# A rate card that is fine (used for ordering cases together with a bad one).
put("card-small.txt", "[acme]\nname = Acme\ncurrency = EUR\nrate = 100\n")


# ---------------------------------------------------------------- timesheets

put("oct-a.txt", """\
# Kai, October 2026: every client, both ways of writing time, other clients' time mixed in
2026-10-01  09:00-09:07  acme/site     7 minutes: up to 15, then the 30 minimum
2026-10-01  09:10-09:40  acme/site     exactly the minimum
2026-10-01  09:45-10:16  acme/site     31 minutes -> 45
2026-10-01  10:30-11:15  acme/brand    exactly 45
2026-10-01  11:15-12:01  acme/brand    46 -> 60
2026-10-02  1h           acme/2d-anim  intro loop
2026-10-02  0h05         acme/2d-anim  tweak
2026-10-02  2h           acme/print    no project rate: the client's
2026-10-02  7m           bolt/app      7 -> 12
2026-10-02  12m          bolt/app      exact
2026-10-02  1h01         bolt/api      61 -> 66
2026-10-03  10:00-10:06  north/web     6 at 80.05 is 8.005
2026-10-03  13:00-13:18  north/app     18 at 80.05 is 24.015
2026-10-05  40m          fjord/rooms   40 -> 45 minimum
2026-10-05  45m          fjord/rooms   45 is the minimum
2026-10-05  46m          fjord/rooms   46 -> 50
2026-10-05  2h03         fjord/spa     123 -> 130
2026-10-06  1h           kite/ads      at 64.10
2026-10-06  33m          kite/web      33 -> 35
2026-10-06  2h47         kite/web      167 -> 170
2026-10-07  3h           lumen/site    pro bono
2026-10-07  1h30         moss/app-2    90 -> 120
2026-10-07  2h01         moss/app-2    121 -> 180
2026-10-07  30m          moss/core     30 -> 60 -> 120 minimum
2026-10-08  2h           zed/web       not in the rate card
2026-10-08  1h           studio/admin  ours
2026-10-30  23:00-23:59  acme/site     late
2026-10-31  4h           acme/brand    last day
""")

put("oct-b.txt", """\
# Rui, October 2026 (tabs between some fields)
2026-10-01\t1h15\tacme/site\tCMS fields
2026-10-01	45m	acme/site	+nobill estimate for the shop
2026-10-02  20m          acme/site    call  +nobill  with Lena
2026-10-09  09:00-12:30  bolt/app     sync bug
2026-10-09  13:00-13:41  bolt/app     sync bug, part 2
2026-10-12  6m           north/web    another 8.005
2026-10-12  30m          north/web    30 at 80.05
2026-10-13  2h15         fjord/spa    booking flow
2026-10-14  25m          kite/ads     tweaks
2026-10-15  4h           moss/core    workshop
2026-10-15  1h           moss/core    follow-up +nobill
2026-09-30  1h           acme/site    the day before October
2026-11-01  1h           acme/site    the day after October
""")

put("span.txt", """\
# Entries on both sides of month and year ends
2026-08-28  1h           acme/site    before the range
2026-08-29  1h10         acme/site    first day of the range
2026-08-31  25m          acme/brand   month end
2026-09-01  2h           acme/site    month start
2026-09-15  50m          acme/site    middle
2026-09-30  15m          acme/brand   month end
2026-10-01  1h           acme/site    month start
2026-10-02  35m          acme/site    last day of the range
2026-10-03  3h           acme/site    after the range
2026-09-30  1h           bolt/app     single day
2026-09-30  14m          bolt/app     single day
2026-10-01  1h           bolt/app     next day
2026-12-31  23:00-23:30  bolt/app     year end
2027-01-01  00:00-00:20  bolt/app     new year
2027-01-02  1h           bolt/app     after
""")

put("cents.txt", """\
# November 2026: amounts and taxes that come out at exactly half a cent
2026-11-02  6m           north/a      6 at 80.05 is 8.005
2026-11-02  18m          north/b      18 at 80.05 is 24.015
2026-11-02  1h42         north/c      102 at 80.05 is 136.085
2026-11-03  6m           tern/a       6 at 12.35 is 1.235
2026-11-03  1h30         tern/b       90 at 12.35 is 18.525
2026-11-04  1h25         wren/x       42.50, 19% of it is 8.075
2026-11-05  1h39         wren/y       49.50, 19% of it is 9.405
2026-11-06  4h05         yarrow/x     245.00, 7.7% of it is 18.865
""")

put("leap.txt", """\
2028-01-31  1h       acme/site   January
2028-02-01  1h       acme/site   first of February
2028-02-28  20m      acme/site   28th
2028-02-29  55m      acme/site   leap day
2028-03-01  2h       acme/site   March
""")

put("feb.txt", """\
2026-01-31  1h       acme/site   January
2026-02-01  31m      acme/site   first of February
2026-02-28  1h       acme/site   last of February
2026-03-01  2h       acme/site   March
""")

put("century.txt", """\
2000-02-29  1h       bolt/app    leap day of a leap century
2000-03-01  1h       bolt/app    March 2000
2100-02-28  2h       bolt/app    last of February 2100
2100-03-01  1h       bolt/app    March 2100
""")

put("nobill.txt", """\
# Which notes mark time as not billed: only the word +nobill on its own
2026-10-01  1h       acme/site   +nobill
2026-10-01  1h       acme/site   kickoff +nobill
2026-10-01  1h       acme/site   +nobill kickoff
2026-10-01  1h       acme/site   kickoff +nobill, then lunch
2026-10-01  1h       acme/site   kickoff (+nobill)
2026-10-01  1h       acme/site   kickoff +NOBILL
2026-10-01  1h       acme/site   kickoff nobill
2026-10-01  1h       acme/site   kickoff +nobillable
2026-10-01  1h       acme/site   kickoff x+nobill
2026-10-01  1h       acme/brand  only not-billed time here +nobill
2026-10-02  1h	acme/site	tabbed	+nobill	note
2026-10-02  15m      acme/site   +nobill +nobill twice is still one entry
""")

put("only-nobill.txt", """\
2026-10-01  1h       acme/site   +nobill workshop
2026-10-02  20m      acme/brand  +nobill
2026-10-03  1h       bolt/app    billed, but bolt
""")

put("one-nobill.txt", """\
2026-10-01  1h       acme/site   billed
2026-10-02  5m       acme/site   +nobill
""")

put("overlap.txt", """\
2026-10-01  09:00-10:00  acme/site   a
2026-10-01  09:30-09:45  acme/site   inside a
2026-10-01  09:50-11:00  acme/brand  starts inside a
2026-10-01  11:00-12:00  acme/site   touches, does not overlap
2026-10-02  09:00-10:00  acme/site   other day
2026-10-02  2h           acme/site   durations never overlap
""")

TS_ERRORS = {
    "bad-date.txt": ("# fine so far\n2026-02-27  1h  acme/site  ok\n2026-02-28  1h  acme/site  ok\n2026-02-29  1h  acme/site  no such day\n", 4),
    "bad-range.txt": ("2026-10-01  1h  acme/site  ok\n2026-10-01  10:00-09:30  acme/site  backwards\n", 2),
    "bad-clock.txt": ("2026-10-01  1h  acme/site  ok\n\n2026-10-01  23:30-24:00  acme/site  no 24:00\n", 3),
    "bad-duration.txt": ("2026-10-01  1h  acme/site  ok\n2026-10-01  1h5  acme/site  minutes need two digits\n", 2),
    "zero-duration.txt": ("2026-10-01  1h  acme/site  ok\n2026-10-01  0m  acme/site  nothing\n", 2),
    "bad-project.txt": ("2026-10-01  1h  acme/site  ok\n2026-10-01  1h  Acme/site  capital\n", 2),
    "short-line.txt": ("2026-10-01  1h  acme/site  ok\n2026-10-01  1h\n", 2),
    "bad-other-client.txt": ("2026-10-01  1h  acme/site  ok\n2026-10-01  1h  zed/web  ok\n2026-10-31  1h  zed/web  ok\n2026-10-32  1h  zed/web  not a date\n", 4),
}
for name, (text, _) in TS_ERRORS.items():
    put(name, text)


def big():
    """A month of a busy team: thousands of entries for acme and moss (and others), deterministic."""
    rng = random.Random(41)
    out = ["# The whole team, October 2026"]
    projects = ["acme/site", "acme/brand", "acme/print", "moss/app-2", "moss/core", "moss/web-3", "bolt/app",
                "studio/admin", "zed/web"]
    for day in range(1, 32):
        for person in range(14):
            minute = 8 * 60 + rng.randrange(0, 60)
            for _ in range(rng.randrange(3, 9)):
                length = rng.choice([5, 7, 12, 15, 20, 25, 30, 45, 50, 60, 61, 75, 90, 119, 120, 150])
                if minute + length >= 24 * 60:
                    break
                project = rng.choice(projects)
                note = rng.choice(["design", "review", "call", "fixes", "+nobill internal", "build", "copy"])
                if rng.random() < 0.5:
                    time = f"{minute // 60:02d}:{minute % 60:02d}-{(minute + length) // 60:02d}:{(minute + length) % 60:02d}"
                elif length % 60 == 0:
                    time = f"{length // 60}h"
                elif length < 60 and rng.random() < 0.5:
                    time = f"{length}m"
                else:
                    time = f"{length // 60}h{length % 60:02d}"
                out.append(f"2026-10-{day:02d}  {time}  {project}  {note} (p{person})")
                minute += length + rng.choice([0, 5, 10, 30])
    return "\n".join(out) + "\n"


put("big.txt", big())
put("ties.txt", TIE_SHEET)

# The docs example: the fixture's rate card and September timesheets.
put("docs-rates.txt", (FIXTURE / "rates.txt").read_text())
put("docs-dana.txt", (FIXTURE / "timesheets" / "2026-09-dana.txt").read_text())
put("docs-omar.txt", (FIXTURE / "timesheets" / "2026-09-omar.txt").read_text())


# ---------------------------------------------------------------- cases

def d(name):
    return f"{DATA_AT}/{name}"


INVOICE = []


def inv(name, args, stderr_has=(), stderr_lacks=(), repo_files=()):
    INVOICE.append({"name": name, "kind": "invoice", "args": ["invoice", *args],
                    "stderr_has": list(stderr_has), "stderr_lacks": list(stderr_lacks),
                    **({"repo_files": list(repo_files)} if repo_files else {})})


CARD = ["--rates", d("card.txt")]
OCT = ["--month", "2026-10", d("oct-a.txt"), d("oct-b.txt")]

inv("docs-example", ["--client", "acme", "--rates", d("docs-rates.txt"), "--month", "2026-09", d("docs-dana.txt"), d("docs-omar.txt")])
inv("docs-bolt", ["--client", "bolt", "--rates", d("docs-rates.txt"), "--month", "2026-09", d("docs-dana.txt"), d("docs-omar.txt")])
inv("docs-north", ["--client", "north", "--rates", d("docs-rates.txt"), "--from", "2026-09-01", "--to", "2026-09-30", d("docs-omar.txt"), d("docs-dana.txt")])
for client in ("acme", "bolt", "north", "fjord", "kite", "lumen", "moss"):
    inv(f"oct-{client}", ["--client", client, *CARD, *OCT])
for client in ("north", "tern", "wren", "yarrow"):
    inv(f"cents-{client}", ["--client", client, *CARD, "--month", "2026-11", d("cents.txt")])
inv("oct-acme-one-file", ["--client", "acme", *CARD, "--month", "2026-10", d("oct-b.txt")])
inv("span-acme", ["--client", "acme", *CARD, "--from", "2026-08-29", "--to", "2026-10-02", d("span.txt")])
inv("span-one-day", ["--client", "bolt", *CARD, "--from", "2026-09-30", "--to", "2026-09-30", d("span.txt")])
inv("span-year-end", ["--client", "bolt", *CARD, "--from", "2026-12-31", "--to", "2027-01-01", d("span.txt")])
inv("month-leap", ["--client", "acme", *CARD, "--month", "2028-02", d("leap.txt")])
inv("month-february", ["--client", "acme", *CARD, "--month", "2026-02", d("feb.txt")])
inv("month-2000", ["--client", "bolt", *CARD, "--month", "2000-02", d("century.txt")])
inv("month-2100", ["--client", "bolt", *CARD, "--month", "2100-02", d("century.txt")])
inv("nobill-words", ["--client", "acme", *CARD, "--month", "2026-10", d("nobill.txt")])
inv("nothing-to-bill", ["--client", "fjord", *CARD, "--month", "2026-12", d("oct-a.txt"), d("oct-b.txt")])
inv("only-not-billed", ["--client", "acme", *CARD, "--month", "2026-10", d("only-nobill.txt")])
inv("one-not-billed", ["--client", "acme", *CARD, "--month", "2026-10", d("one-nobill.txt")])
inv("other-client-only", ["--client", "lumen", *CARD, "--month", "2026-10", d("only-nobill.txt")])
inv("big-moss", ["--client", "moss", *CARD, "--month", "2026-10", d("big.txt")])
inv("big-acme", ["--client", "acme", *CARD, "--from", "2026-10-03", "--to", "2026-10-27", d("big.txt"), d("oct-a.txt")])
inv("ties-quill", ["--client", "quill", *CARD, "--month", "2026-12", d("ties.txt")])
inv("ties-sable", ["--client", "sable", *CARD, "--from", "2026-12-01", "--to", "2026-12-31", d("ties.txt")])

# The repository's own files where they are, as people run the command from the repository root: the docs example
# exactly as written, relative paths for another client, absolute paths into the repository, and a timesheet that is
# not there yet.
SEPT = ["timesheets/2026-09-dana.txt", "timesheets/2026-09-omar.txt"]
REPO = {"repo_files": ["rates.txt", *SEPT]}
inv("repo-docs-example", ["--client", "acme", "--rates", "rates.txt", "--month", "2026-09", *SEPT], **REPO)
inv("repo-bolt", ["--client", "bolt", "--rates", "rates.txt", "--from", "2026-09-01", "--to", "2026-09-30",
                  *reversed(SEPT)], **REPO)
inv("repo-north-absolute", ["--client", "north", "--rates", f"{CODE_AT}/rates.txt", "--month", "2026-09",
                            *(f"{CODE_AT}/{p}" for p in SEPT)], **REPO)
inv("repo-no-october-yet", ["--client", "acme", "--rates", "rates.txt", "--month", "2026-10", SEPT[0],
                            "timesheets/2026-10-dana.txt"],
    stderr_has=["hours invoice: cannot read", "timesheets/2026-10-dana.txt"], **REPO)

# Files with a mistake, and files that are not there: exit 1, nothing on standard output.
for name, (_, line) in TS_ERRORS.items():
    inv(f"timesheet-{name[:-4]}", ["--client", "acme", *CARD, "--month", "2026-10", d("oct-a.txt"), d(name)],
        stderr_has=[f"{name}:{line}"])
inv("timesheet-missing", ["--client", "acme", *CARD, "--month", "2026-10", d("oct-a.txt"), d("missing.txt")],
    stderr_has=["hours invoice: cannot read", "missing.txt"])
for name, (_, line) in RATE_ERRORS.items():
    inv(f"card-{name[6:-4]}", ["--client", "ok", "--rates", d(name), "--month", "2026-10", d("oct-a.txt")],
        stderr_has=[f"{name}:{line}"])
inv("card-missing", ["--client", "acme", "--rates", d("no-card.txt"), "--month", "2026-10", d("oct-a.txt")],
    stderr_has=["hours invoice: cannot read", "no-card.txt"])
inv("client-not-in-card", ["--client", "zed", *CARD, "--month", "2026-10", d("oct-a.txt")],
    stderr_has=['hours invoice: no client "zed"'])

# Order: command line, rate card, client, timesheets in order; only the first mistake is reported.
inv("order-card-before-client", ["--client", "zed", "--rates", d("rates-bad-rate.txt"), "--month", "2026-10", d("oct-a.txt")],
    stderr_has=["rates-bad-rate.txt:8"], stderr_lacks=['"zed"'])
inv("order-card-before-timesheet", ["--client", "ok", "--rates", d("rates-high-tax.txt"), "--month", "2026-10", d("bad-date.txt")],
    stderr_has=["rates-high-tax.txt:5"], stderr_lacks=["bad-date.txt"])
inv("order-client-before-timesheet", ["--client", "zed", *CARD, "--month", "2026-10", d("bad-range.txt")],
    stderr_has=['hours invoice: no client "zed"'], stderr_lacks=["bad-range.txt"])
inv("order-first-timesheet", ["--client", "acme", *CARD, "--month", "2026-10", d("bad-duration.txt"), d("bad-date.txt")],
    stderr_has=["bad-duration.txt:2"], stderr_lacks=["bad-date.txt"])
inv("order-missing-before-bad", ["--client", "acme", *CARD, "--month", "2026-10", d("missing.txt"), d("bad-date.txt")],
    stderr_has=["hours invoice: cannot read", "missing.txt"], stderr_lacks=["bad-date.txt"])

# Command-line mistakes: exit 2 before anything is read (the rate card in some of them is broken too).
USAGE = [
    ("no-client", ["--rates", d("card.txt"), "--month", "2026-10", d("oct-a.txt")]),
    ("no-rates", ["--client", "acme", "--month", "2026-10", d("oct-a.txt")]),
    ("no-period", ["--client", "acme", *CARD, d("oct-a.txt")]),
    ("month-and-range", ["--client", "acme", *CARD, "--month", "2026-10", "--from", "2026-10-01", "--to", "2026-10-31", d("oct-a.txt")]),
    ("month-and-from", ["--client", "acme", *CARD, "--month", "2026-10", "--from", "2026-10-01", d("oct-a.txt")]),
    ("from-only", ["--client", "acme", *CARD, "--from", "2026-10-01", d("oct-a.txt")]),
    ("to-only", ["--client", "acme", *CARD, "--to", "2026-10-31", d("oct-a.txt")]),
    ("month-13", ["--client", "acme", *CARD, "--month", "2026-13", d("oct-a.txt")]),
    ("month-short", ["--client", "acme", *CARD, "--month", "2026-9", d("oct-a.txt")]),
    ("month-day", ["--client", "acme", *CARD, "--month", "2026-10-01", d("oct-a.txt")]),
    ("date-not-real", ["--client", "acme", *CARD, "--from", "2026-09-31", "--to", "2026-10-31", d("oct-a.txt")]),
    ("date-format", ["--client", "acme", *CARD, "--from", "2026/10/01", "--to", "2026-10-31", d("oct-a.txt")]),
    ("from-after-to", ["--client", "acme", *CARD, "--from", "2026-10-02", "--to", "2026-10-01", d("oct-a.txt")]),
    ("unknown-option", ["--client", "acme", *CARD, "--month", "2026-10", "--format", "csv", d("oct-a.txt")]),
    ("no-timesheet", ["--client", "acme", *CARD, "--month", "2026-10"]),
    ("before-card", ["--client", "ok", "--rates", d("rates-bad-rate.txt"), d("oct-a.txt")]),
    ("before-client", ["--client", "zed", *CARD, "--from", "2026-10-01", d("oct-a.txt")]),
]
for name, args in USAGE:
    inv(f"usage-{name}", args, stderr_has=["hours invoice:"])


EXISTING = []


def existing(name, args, compare_stderr=True, stderr_has=()):
    EXISTING.append({"name": name, "kind": "existing", "args": args, "compare_stderr": compare_stderr,
                     **({"stderr_has": list(stderr_has)} if stderr_has else {})})


existing("report-projects", ["report", d("oct-a.txt"), d("oct-b.txt")])
existing("report-clients-range", ["report", "--by", "client", "--from", "2026-09-01", "--to", "2026-10-15", d("span.txt"), d("big.txt")])
existing("report-dates", ["report", "--by", "date", d("leap.txt"), d("century.txt")])
existing("report-bad", ["report", d("oct-a.txt"), d("bad-range.txt")])
# Usage errors: exit status 2, nothing on standard output, and the command named; the usage text itself is not compared.
REPORT_USAGE = {"stderr_has": ["hours report: "], "compare_stderr": False}
existing("report-usage", ["report", "--by", "week", d("oct-a.txt")], **REPORT_USAGE)
existing("report-usage-none", ["report"], **REPORT_USAGE)
existing("report-usage-date", ["report", "--from", "2026-3-1", d("oct-a.txt")], **REPORT_USAGE)
existing("report-usage-option", ["report", "--bogus", d("oct-a.txt")], **REPORT_USAGE)
existing("check-clean", ["check", d("oct-a.txt"), d("nobill.txt"), d("big.txt")])
existing("check-problems", ["check", d("overlap.txt"), d("oct-b.txt"), d("bad-date.txt"), d("missing.txt")])
# Each kind of bad line the timesheet reader reports, one per file, through the command line.
existing("check-bad-lines", ["check", d("bad-clock.txt"), d("bad-duration.txt"), d("zero-duration.txt"), d("bad-project.txt"),
                             d("short-line.txt")])


# ---------------------------------------------------------------- expected results

def fixture_hours(args):
    """The fixture's own hours on args, with the code and the data at the check's paths."""
    node = shutil.which("node")
    cmd = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", "/tmp", "--dev", "/dev", "--proc", "/proc", "--unshare-net",
           "--die-with-parent", "--ro-bind", str(FIXTURE), CODE_AT, "--ro-bind", str(DATA), DATA_AT,
           "--chdir", CODE_AT, "--", node, f"{CODE_AT}/bin/hours.ts", *args]
    r = subprocess.run(cmd, capture_output=True, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8", "TZ": "UTC"})
    return r.returncode, r.stdout, r.stderr


def local(case, path):
    """A file named in a case, as a path here: the check's data directory mapped to data/ here, and the repository
    (absolute paths into it, or relative ones, which the check resolves from the repository root) to the fixture."""
    path = path.replace(DATA_AT, str(DATA)).replace(CODE_AT, str(FIXTURE))
    return os.path.join(FIXTURE, path) if case.get("repo_files") else path


def reference_at(case):
    """reference.run on the case, run in the fixture (the repository root) with the check's paths mapped to here;
    the paths in its messages mapped back."""
    args = [a.replace(DATA_AT, str(DATA)).replace(CODE_AT, str(FIXTURE)) for a in case["args"]]
    here = os.getcwd()
    os.chdir(FIXTURE)
    try:
        status, out, err = reference.run(args)
    finally:
        os.chdir(here)
    return status, out.encode(), err.replace(str(DATA), DATA_AT).replace(str(FIXTURE), CODE_AT).encode()


def money_lines(case, port=None):
    """The amounts a successful invoice prints, as strings: exactly (whole cents, as the spec says) when port is
    None, otherwise the way port, (kind, amount, tax) as described under "money in floats", computes them. None when
    the case is not a successful invoice."""
    try:
        client_id, rates_path, first, last, files = reference.parse_args(case["args"][1:])
        client = reference.read_rates(local(case, rates_path))[client_id]
        entries = [e for path in files for e in reference.read_timesheet(local(case, path))]
    except (reference.Failure, KeyError):
        return None
    billed = {}
    for day, minutes, owner, project, words in entries:
        if owner == client_id and first <= day <= last and "+nobill" not in words:
            inc = client["increment"]
            billed[project] = billed.get(project, 0) + max((minutes + inc - 1) // inc * inc, client["minimum"])
    if not billed:
        return None
    rates = [(billed[p], client["projects"].get(p.split("/", 1)[1], client["rate"])) for p in sorted(billed)]
    t = client["tax"]
    if port is None:
        cents = [reference.half_up(m * c, 60) for m, c in rates]
        tax = reference.half_up(sum(cents) * t, 100_00)
        return [reference.amount(x) for x in [*cents, sum(cents), tax, sum(cents) + tax]]
    kind, amount, tax_of = port
    if kind == "cents":
        cents = [amount(m, c) for m, c in rates]
        tax = tax_of(sum(cents), t)
        return [reference.amount(x) for x in [*cents, sum(cents), tax, sum(cents) + tax]]
    shown, subtotal = [], 0
    for m, c in rates:
        value = js_round(amount(m, c) * 100) / 100
        subtotal += value
        shown.append(f"{value:.2f}")
    tax = js_round(tax_of(subtotal, t) * 100) / 100
    return shown + [f"{subtotal:.2f}", f"{tax:.2f}", f"{subtotal + tax:.2f}"]


def careless_ports():
    """{label: port} for every careless way of doing the money modeled here."""
    ports = {f"{a} and {t}": ("units", fa, ft)
             for a, fa in UNITS_AMOUNTS.items() for t, ft in UNITS_TAXES.items()}
    ports.update({f"{a} and exact tax": ("cents", fa, EXACT_TAX) for a, fa in CENTS_AMOUNTS.items()})
    ports.update({f"exact amounts and {t}": ("units", EXACT_UNITS_AMOUNT, ft) for t, ft in UNITS_TAXES.items()})
    return ports


def main():
    if DATA.exists():
        shutil.rmtree(DATA)
    if EXPECTED.exists():
        shutil.rmtree(EXPECTED)
    DATA.mkdir()
    EXPECTED.mkdir()
    for name, text in sorted(FILES.items()):
        (DATA / name).write_text(text)

    cases = []
    for case in INVOICE:
        status, out, err = reference_at(case)
        for want in case["stderr_has"]:
            assert want in err.decode(), (case["name"], want, err)
        for unwanted in case["stderr_lacks"]:
            assert unwanted not in err.decode(), (case["name"], unwanted, err)
        assert (status == 0) == (out != b""), case["name"]
        (EXPECTED / f"{case['name']}.out").write_bytes(out)
        cases.append(dict(case, status=status))
    for case in EXISTING:
        status, out, err = fixture_hours(case["args"])
        assert status in (0, 1, 2) and (out or err), (case["name"], status, err)
        for want in case.get("stderr_has", []):
            assert want in err.decode(), (case["name"], want, err)
        (EXPECTED / f"{case['name']}.out").write_bytes(out)
        if case["compare_stderr"]:
            (EXPECTED / f"{case['name']}.err").write_bytes(err)
        cases.append(dict(case, status=status))
    names = [c["name"] for c in cases]
    assert len(names) == len(set(names))
    (HERE / "cases.json").write_text(json.dumps(cases, indent=1) + "\n")

    # The document's example is what the reference prints.
    doc = (FIXTURE / "docs" / "invoice.md").read_text()
    block = re.search(r"\n    \$ hours invoice [^\n]*\n((?:    [^\n]*\n|\n)+?)\nLine by line", doc).group(1)
    shown = "".join(l[4:] + "\n" if l else "\n" for l in block.rstrip("\n").split("\n"))
    assert shown == (EXPECTED / "docs-example.out").read_text(), "docs/invoice.md example differs from the reference"

    # The docs example run from the repository root as written prints the same.
    assert (EXPECTED / "repo-docs-example.out").read_bytes() == (EXPECTED / "docs-example.out").read_bytes()

    # Money in floats gets successful cases wrong, whichever common way the arithmetic is written (and the docs
    # example right, so it alone does not tell); whole cents with an exact product get none wrong.
    caught = []
    for label, port in careless_ports().items():
        wrong = [c["name"] for c in INVOICE if money_lines(c) != money_lines(c, port)]
        assert "docs-example" not in wrong, label
        assert len(wrong) >= (2 if "exact amounts" not in label else 1), (label, wrong)
        caught.append(f"{label}: {len(wrong)}")
    exact = ("cents", EXACT_AMOUNT, EXACT_TAX)
    assert all(money_lines(c) == money_lines(c, exact) for c in INVOICE), "whole cents with Math.round fail a case"
    ok = sum(1 for c in cases if c["kind"] == "invoice" and c["status"] == 0)
    print(f"{len(INVOICE)} invoice cases ({ok} successful), {len(EXISTING)} existing-command cases; "
          f"cases float money gets wrong: {'; '.join(caught)}")


if __name__ == "__main__":
    main()
