"""Writes hidden/cases.json for ssot-rules-rs: hidden race files (inputs only) and the command lines the
check runs on them. Expected results come from reference.py at check time, under the fixture's Portsmouth
Numbers and under each edited list. Run it from anywhere; it also prints how each edit changes the outputs,
and refuses a case set where an edit would leave either command's outputs unchanged, where two classes of a
pursuit start at the same second under any list, or where a class's number shows in no pursuit run again
under the whole new list."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reference as ref  # noqa: E402

RACES = {
    "club-sunday.race": """# Sunday club race, course 5, three laps
race Sunday Club Race 14
start 13:30:00
boat 188214 | Kate Morrow   | ILCA 6     | 14:39:12
boat 190002 | Nils Berg     | ILCA 6     | 14:41:05
boat 177345 | Hana Sato     | ILCA 6     | 14:44:40
boat 207101 | Ann Hale      | ILCA 7     | 14:36:30
boat 209988 | Joe Marsh     | ILCA 7     | 14:38:20
boat 1432   | Raj Patel     | Topper     | 14:51:50
boat 1460   | Ollie Grant   | Topper     | 14:55:02
boat 70412  | Grace Okafor  | Mirror     | 14:52:40
boat 2210   | Lee Wong      | Optimist   | 15:10:05
boat 2215   | Ruby Wong     | Optimist   | 15:14:31
boat 5120   | Tom Becker    | Solo       | 14:40:11
boat 1290   | Alex Rowe     | RS200      | 14:31:58
""",
    "regatta-dnf.race": """race Junior Regatta, race 2
start 11:00:00
boat 2210 | Lee Wong     | Optimist | 11:58:20
boat 2215 | Ruby Wong    | Optimist | DNF
boat 2301 | Sofia Lind   | Optimist | 12:01:44
boat 1432 | Raj Patel    | Topper   | 11:50:31
boat 1477 | Isla Ferris  | Topper   | DNS
boat 1460 | Ollie Grant  | Topper   | 11:49:58
boat 70412 | Grace Okafor | Mirror  | 11:51:15
boat 70499 | Finn Doyle   | Mirror  | 11:53:40
""",
    "evening-crlf.race": "race Wednesday Evening 6\r\nstart 18:45:00\r\n"
                         "boat 188214 | Kate Morrow | ILCA 6 | 19:31:40\r\n"
                         "boat 14102 | Pat Quinn | GP14 | 19:33:15\r\n"
                         "boat 690 | Bea Cole | Comet | 19:38:01\r\n"
                         "boat 190002 | Nils Berg | ILCA 6 | 19:30:59\r\n"
                         "boat 21001 | Eli Hart | Enterprise | 19:32:22\r\n",
    "tie.race": """race Tie-break
start 10:00:00
boat 1460 | Ollie Grant | Topper | 11:08:12
boat 1432 | Raj Patel   | Topper | 11:08:12
boat 207101 | Ann Hale  | ILCA 7 | 10:55:00
boat 188214 | Kate Morrow | ILCA 6 | 10:57:21
""",
    "unknown-class.race": """race Open Meeting
start 12:00:00
boat 1 | Al Brook | ILCA 7 | 13:00:00
boat 2 | Cy Dale | Laser 2000 | 13:02:00
""",
    "unfinished.race": """race Still Out
start 12:00:00
boat 1 | Al Brook | ILCA 7 | 13:00:00
boat 2 | Cy Dale | Solo
""",
    "winter-2.race": """# Winter Pursuit 2 entries
race Winter Pursuit 2
start 10:30:00
boat 2210   | Lee Wong      | Optimist
boat 2215   | Ruby Wong     | Optimist
boat 1432   | Raj Patel     | Topper
boat 1460   | Ollie Grant   | Topper
boat 70412  | Grace Okafor  | Mirror
boat 188214 | Kate Morrow   | ILCA 6
boat 190002 | Nils Berg     | ILCA 6
boat 207101 | Ann Hale      | ILCA 7
boat 1011   | Dev Sharma    | RS400
boat 5120   | Tom Becker    | Solo
boat 3301   | Sam Ito       | Wayfarer
boat 690    | Bea Cole      | Comet
""",
    "winter-3.race": """race Winter Pursuit 3
start 11:00:00
boat 1432   | Raj Patel     | Topper
boat 1460   | Ollie Grant   | Topper
boat 70412  | Grace Okafor  | Mirror
boat 188214 | Kate Morrow   | ILCA 6
boat 5120   | Tom Becker    | Solo
boat 2988   | Mia Lund      | RS Feva XL
""",
    "sailed.race": """# Sailed last week; finish times are in, pursuit ignores them
race Ice Breaker
start 12:15:00
boat 188214 | Kate Morrow | ILCA 6     | 13:20:41
boat 207101 | Ann Hale    | ILCA 7     | DNF
boat 501    | Max Ure     | Finn       | 13:12:09
boat 1499   | Zoe Park    | RS Aero 7  |
""",
    "juniors-crlf.race": "race Juniors Long Distance\r\nstart 09:00:00\r\n"
                         "boat 2210 | Lee Wong | Optimist\r\n"
                         "boat 203300 | Ivy Shaw | ILCA 4\r\n"
                         "boat 1011 | Dev Sharma | RS400\r\n",
    "one-class.race": """race ILCA 6 Training
start 16:00:00
boat 188214 | Kate Morrow | ILCA 6
boat 190002 | Nils Berg   | ILCA 6
boat 177345 | Hana Sato   | ILCA 6
""",
    "club-boats.race": """# The club's own boats, for members without a dinghy of their own
race Club Boats Pursuit
start 14:00:00
boat 21001  | Eli Hart      | Enterprise
boat 14102  | Pat Quinn     | GP14
boat 1290   | Alex Rowe     | RS200
boat 3301   | Sam Ito       | Wayfarer
boat 501    | Max Ure       | Finn
""",
    "laser-entry.race": """race Winter Pursuit 4
start 10:30:00
boat 2210 | Lee Wong | Optimist
boat 4471 | Gus Tate | Laser 2000
""",
    "no-boats.race": """race Winter Pursuit 5
start 10:30:00
# entries close Friday
""",
    "bad-line.race": """race Winter Pursuit 6
start 10:30:00
boat 2210 | Lee Wong | Optimist
boat 1432 | Raj Patel | Topper | 11:7:00
""",
}

RESULTS = [  # (name, file, run under each edit)
    ("results-club-sunday", "club-sunday.race", True),
    ("results-dnf-dns", "regatta-dnf.race", True),
    ("results-crlf", "evening-crlf.race", True),
    ("results-tie", "tie.race", True),
    ("results-unknown-class", "unknown-class.race", False),
    ("results-unfinished", "unfinished.race", False),
]
PURSUIT = [  # (name, file, minutes or None, run under each edit)
    ("pursuit-twelve-boats", "winter-2.race", None, True),
    ("pursuit-no-optimist-45", "winter-3.race", 45, True),
    ("pursuit-ignores-finishes-90", "sailed.race", 90, True),
    ("pursuit-crlf-600", "juniors-crlf.race", 600, True),
    ("pursuit-one-class-5", "one-class.race", 5, True),
    ("pursuit-club-boats-75", "club-boats.race", 75, True),
    ("pursuit-unknown-class", "laser-entry.race", None, False),
    ("pursuit-no-boats", "no-boats.race", 30, False),
    ("pursuit-bad-line", "bad-line.race", None, False),
    ("pursuit-missing-file", "none.race", None, False),
]
USAGE = [  # (name, arguments after `startline`), all exit status 2
    ("usage-no-file", ["pursuit"]),
    ("usage-minutes-0", ["pursuit", "--minutes", "0", "{dir}/winter-2.race"]),
    ("usage-minutes-601", ["pursuit", "--minutes", "601", "{dir}/winter-2.race"]),
    ("usage-minutes-word", ["pursuit", "--minutes", "ninety", "{dir}/winter-2.race"]),
    ("usage-minutes-missing", ["pursuit", "{dir}/winter-2.race", "--minutes"]),
    ("usage-two-files", ["pursuit", "{dir}/winter-2.race", "{dir}/winter-3.race"]),
    ("usage-unknown-option", ["pursuit", "--fast", "{dir}/winter-2.race"]),
]
EDITS = [("ilca-6", {"ILCA 6": 1139}), ("optimist", {"Optimist": 1611}), ("topper", {"Topper": 1390})]
# Next March's whole new list, made where the ILCA 6 edit landed: every class's number up by RISE.
RISE = 7
WHOLE = ("all-classes", {c: n + RISE for c, n in ref.PN.items()})


def classes_in(text):
    return {line.split("|")[2].strip() for line in text.splitlines() if line.strip().startswith("boat")}


def outputs(pn):
    r = [ref.results(RACES[f], pn) for _, f, again in RESULTS if again]
    p = [ref.pursuit(RACES[f], m or 60, pn) for _, f, m, again in PURSUIT if again]
    return r, p


def no_ties(pursuits, label):
    for (name, f, m, _), out in zip([x for x in PURSUIT if x[3]], pursuits):
        assert out[0] == 0, (name, out)
        offsets = [l.split()[0] for l in out[1].splitlines()[2:]]
        assert len(offsets) == len(set(offsets)), f"{name}: two classes start at the same second ({label})"


def main():
    base = outputs(ref.PN)
    for (name, f, _), out in zip([x for x in RESULTS if x[2]], base[0]):
        assert out[0] == 0, (name, out)
    no_ties(base[1], "fixture's list")
    for name, edit in EDITS + [WHOLE]:
        r, p = outputs(ref.with_pn(classes=edit))
        no_ties(p, name)
        changed_r = sum(a != b for a, b in zip(base[0], r))
        changed_p = sum(a != b for a, b in zip(base[1], p))
        print(f"{name}: results cases changed {changed_r}, pursuit cases changed {changed_p}")
        assert changed_r and changed_p, name
    # Under the whole new list, every class must show in some pursuit run again, so that a startline keeping
    # its own number for any one class gives a different output.
    whole = outputs(ref.with_pn(classes=WHOLE[1]))[1]
    for cls in ref.PN:
        kept = outputs(ref.with_pn(classes={**WHOLE[1], cls: ref.PN[cls]}))[1]
        assert kept != whole, f"no pursuit run again shows the number for {cls}"
    doc = {"note": "Inputs only: expected results come from reference.py at check time, under the fixture's Portsmouth Numbers and under each edited list. {dir} is the directory holding the race files.",
           "races": RACES,
           "results": [{"name": n, "file": f, "again": a} for n, f, a in RESULTS],
           "pursuit": [{"name": n, "file": f, "minutes": m, "again": a} for n, f, m, a in PURSUIT],
           "usage": [{"name": n, "args": a} for n, a in USAGE]}
    (HERE / "cases.json").write_text(json.dumps(doc, indent=1) + "\n")


if __name__ == "__main__":
    main()
