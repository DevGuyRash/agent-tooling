"""Writes cases.json: the hidden exports and the commands the check runs on them. Expected output is not
stored; check.py computes it with reference.py under the documented rule and under each edit.

Three kinds of case. policy: inputs on which the fixture's three copies of the rule, each with the request
applied, all agree (no item exactly 3 days late, no children's item owing more than 2.50, no media item
owing more than 10.00), so they show the request: adult 0.35 a day and the device category. drift: inputs
on which those copies disagree, for every command, so they show whether the drift was resolved to
docs/fines.md. existing: behavior the request does not touch (exports with a byte-order mark, columns in
another order, categories in any case, refusals, among them a category the policy does not know in every
command, empty results, the kiosk's block at exactly 10.00, bad command lines). check.py verifies the policy/drift split and that every edit it makes changes some output of
every command before each run.

Run from this directory: python3 make_cases.py"""
import json
from pathlib import Path

ON = "2026-11-20"
HEADER = "loan_id,patron_id,barcode,title,category,due,returned\n"
PATRONS = ("patron_id,name\n"
           "P-4101,Grace Achterberg\n"
           "P-4102,Tomás Ferreira\n"
           "P-4103,Li Wei\n"
           "P-4104,Oskar van Dijk\n"
           "P-4105,amara Nwosu\n")


def loans(rows):
    return HEADER + "".join(",".join(r) + "\n" for r in rows)


# Returned loans: (id, patron, barcode, title, category, due, returned).
POLICY_RETURNED = [
    ("L-51001", "P-4101", "31207002110014", "The Remains of the Day", "adult", "2026-11-02", "2026-11-08"),   # 6 days
    ("L-51002", "P-4101", "31207002110022", "Middlemarch", "adult", "2026-11-03", "2026-11-05"),              # 2 days
    ("L-51003", "P-4102", "31207002110030", "Pachinko", "adult", "2026-11-04", "2026-11-05"),                 # 1 day
    ("L-51004", "P-4102", "31207002110048", "The Overstory", "adult", "2026-11-06", "2026-11-01"),            # early
    ("L-51005", "P-4104", "31207002110055", "Wolf Hall", "adult", "2026-10-10", "2026-11-04"),                # 25 days
    ("L-51006", "P-4103", "31207002110063", "The Gruffalo", "children", "2026-11-02", "2026-11-07"),          # 5 days
    ("L-51007", "P-4104", "31207002110071", "Holes", "children", "2026-10-20", "2026-11-05"),                 # 16 days
    ("L-51008", "P-4104", "31207002110089", "Paddington", "media", "2026-11-05", "2026-11-09"),               # 4 days
    ("L-51009", "P-4105", "31207002110097", "Zelda: Tears of the Kingdom", "media", "2026-11-01", "2026-11-09"),  # 8
    ("L-51010", "P-4105", "31207002110105", "Laptop 07", "device", "2026-11-10", "2026-11-14"),               # 4 days
    ("L-51011", "P-4101", "31207002110113", "Hotspot 03", "device", "2026-11-01", "2026-11-13"),              # 12 days
    ("L-51012", "P-4102", "31207002110121", "Laptop 12", "device", "2026-10-25", "2026-11-13"),               # 19 days
    ("L-51013", "P-4104", "31207002110139", "Laptop 02", "device", "2026-10-20", "2026-11-15"),               # 26 days
    ("L-51014", "P-4103", "31207002110147", "Hotspot 09", "device", "2026-11-12", "2026-11-14"),              # 2 days
]
# Loans still out on ON.
POLICY_OUT = [
    ("L-51101", "P-4101", "31207002120013", "A Little Life", "adult", "2026-11-10", ""),       # 10 days
    ("L-51102", "P-4102", "31207002120021", "Babel", "adult", "2026-11-18", ""),               # 2 days
    ("L-51103", "P-4102", "31207002120039", "Matilda", "children", "2026-11-06", ""),          # 14 days
    ("L-51104", "P-4103", "31207002120047", "Spirited Away", "media", "2026-11-15", ""),       # 5 days
    ("L-51105", "P-4104", "31207002120054", "Laptop 05", "device", "2026-11-13", ""),          # 7 days
    ("L-51106", "P-4105", "31207002120062", "Hotspot 11", "device", "2026-11-01", ""),         # 19 days
    ("L-51107", "P-4101", "31207002120070", "Laptop 09", "device", "2026-10-20", ""),          # 31 days
    ("L-51108", "P-4104", "31207002120088", "Bleak House", "adult", "2026-10-01", ""),         # 50 days
    ("L-51109", "P-4105", "31207002120096", "The BFG", "children", "2026-11-16", ""),          # 4 days
    ("L-51110", "P-4104", "31207002120104", "Mario Kart 8", "media", "2026-11-19", ""),        # 1 day
    ("L-51111", "P-4102", "31207002120112", "Arrival", "media", "2026-11-14", ""),             # 6 days
]
DRIFT_RETURNED = [
    ("L-52001", "P-4101", "31207002130012", "Normal People", "adult", "2026-11-02", "2026-11-05"),       # 3 days
    ("L-52002", "P-4102", "31207002130020", "Wonder", "children", "2026-10-15", "2026-11-04"),           # 20 days
    ("L-52003", "P-4103", "31207002130038", "Coraline", "children", "2026-10-12", "2026-11-05"),         # 24 days
    ("L-52004", "P-4104", "31207002130046", "Dune Part Two", "media", "2026-11-01", "2026-11-10"),       # 9 days
    ("L-52005", "P-4105", "31207002130053", "Elden Ring", "media", "2026-10-28", "2026-11-10"),          # 13 days
    ("L-52006", "P-4101", "31207002130061", "Laptop 14", "device", "2026-11-10", "2026-11-13"),          # 3 days
    ("L-52007", "P-4102", "31207002130079", "Charlotte's Web", "children", "2026-11-02", "2026-11-05"),  # 3 days
]
DRIFT_OUT = [
    ("L-52101", "P-4103", "31207002140011", "Klara and the Sun", "adult", "2026-11-17", ""),   # 3 days
    ("L-52102", "P-4104", "31207002140029", "The Hobbit", "children", "2026-10-30", ""),       # 21 days
    ("L-52103", "P-4105", "31207002140037", "Past Lives", "media", "2026-11-09", ""),          # 11 days
    ("L-52104", "P-4102", "31207002140045", "Hotspot 01", "device", "2026-11-17", ""),         # 3 days
    ("L-52105", "P-4101", "31207002140052", "Oppenheimer", "media", "2026-11-17", ""),         # 3 days
]

FILES = {
    "policy-loans.csv": loans(POLICY_RETURNED + POLICY_OUT),
    "patrons.csv": PATRONS,
    "drift-loans.csv": loans(DRIFT_RETURNED + DRIFT_OUT),
    # Existing behavior: a byte-order mark on both exports, as the library system writes them.
    "bom-loans.csv": "\ufeff" + loans([
        ("L-53001", "P-4201", "31207002150010", "Goodnight Moon", "children", "2026-11-02", "2026-11-07"),
        ("L-53002", "P-4201", "31207002150028", "Fargo", "media", "2026-11-15", ""),
    ]),
    "bom-patrons.csv": "\ufeffpatron_id,name\nP-4201,Saoirse Byrne\n",
    # Columns in another order, values with spaces, categories in any case.
    "reordered-loans.csv": (
        "title,category,loan_id,due,returned,barcode,patron_id\n"
        "Chungking Express, Media ,L-53101,2026-11-05,2026-11-09,31207002160019, P-4301 \n"
        "Where the Wild Things Are,CHILDREN,L-53102, 2026-11-01 ,2026-11-07 ,31207002160027,P-4301\n"
        "Amélie,MEDIA,L-53103,2026-11-12,,31207002160035,P-4301\n"),
    "reordered-patrons.csv": "name,patron_id\nNiamh O'Connell,P-4301\n",
    "unknown-category.csv": loans([
        ("L-53201", "P-4101", "31207002170018", "Zine of the Month", "zines", "2026-11-02", "2026-11-09")]),
    # A category the policy does not know, on a loan still out and inside its grace period, beside an
    # ordinary overdue loan of the same patron: every command refuses the export.
    "unknown-category-out.csv": loans([
        ("L-53251", "P-4101", "31207002170026", "Persepolis", "adult", "2026-11-10", ""),
        ("L-53252", "P-4101", "31207002170034", "Zine of the Week", "zines", "2026-11-19", ""),
    ]),
    "unknown-patron.csv": loans([
        ("L-53301", "P-4999", "31207002180017", "Stig of the Dump", "children", "2026-11-10", "")]),
    "no-fines.csv": loans([
        ("L-53401", "P-4101", "31207002190016", "Emma", "adult", "2026-11-10", "2026-11-09"),
        ("L-53402", "P-4101", "31207002190024", "Persuasion", "adult", "2026-11-10", "2026-11-11"),
        ("L-53403", "P-4102", "31207002190032", "Heidi", "children", "2026-11-25", ""),
    ]),
    "block-at-ten.csv": loans([
        ("L-53501", "P-4105", "31207002200013", "Totoro", "media", "2026-11-01", "2026-11-09")]),  # 8 days
    "no-category-column.csv": "loan_id,patron_id,barcode,title,due,returned\nL-1,P-4101,312,Emma,2026-11-01,\n",
    "bad-date.csv": loans([("L-53601", "P-4101", "31207002210012", "Emma", "adult", "2026-11-31", "")]),
}


def case(name, kind, *args, expect=None):
    c = {"name": name, "kind": kind, "args": list(args)}
    if expect:
        c["expect"] = expect
    return c


def receipts(kind, rows, file):
    return [case(f"{kind}:receipt:{r[0]}", kind, "receipt", "{" + file + "}", r[0]) for r in rows]


def accounts(kind, file, rows):
    ids = sorted({r[1] for r in rows})
    return [case(f"{kind}:account:{p}", kind, "account", "{" + file + "}", "{patrons.csv}", p, "--on", ON) for p in ids]


CASES = (
    receipts("policy", POLICY_RETURNED, "policy-loans.csv")
    + [case("policy:notices", "policy", "notices", "{policy-loans.csv}", "{patrons.csv}", "--on", ON),
       case("policy:notices:2026-11-12", "policy", "notices", "{policy-loans.csv}", "{patrons.csv}", "--on", "2026-11-12")]
    + accounts("policy", "policy-loans.csv", POLICY_RETURNED + POLICY_OUT)
    + receipts("drift", DRIFT_RETURNED, "drift-loans.csv")
    + [case("drift:notices", "drift", "notices", "{drift-loans.csv}", "{patrons.csv}", "--on", ON)]
    + accounts("drift", "drift-loans.csv", DRIFT_RETURNED + DRIFT_OUT)
    + [
        case("existing:receipt:bom", "existing", "receipt", "{bom-loans.csv}", "L-53001"),
        case("existing:notices:bom", "existing", "notices", "{bom-loans.csv}", "{bom-patrons.csv}", "--on", ON),
        case("existing:account:bom", "existing", "account", "{bom-loans.csv}", "{bom-patrons.csv}", "P-4201", "--on", ON),
        case("existing:receipt:reordered-media", "existing", "receipt", "{reordered-loans.csv}", "L-53101"),
        case("existing:receipt:reordered-children", "existing", "receipt", "{reordered-loans.csv}", "L-53102"),
        case("existing:account:reordered", "existing", "account", "{reordered-loans.csv}", "{reordered-patrons.csv}", "P-4301",
             "--on", ON),
        case("existing:receipt:unknown-loan", "existing", "receipt", "{policy-loans.csv}", "L-59999"),
        case("existing:receipt:still-out", "existing", "receipt", "{policy-loans.csv}", "L-51101"),
        case("existing:receipt:unknown-category", "existing", "receipt", "{unknown-category.csv}", "L-53201"),
        case("existing:notices:unknown-category", "existing", "notices", "{unknown-category-out.csv}", "{patrons.csv}",
             "--on", ON),
        case("existing:account:unknown-category", "existing", "account", "{unknown-category-out.csv}", "{patrons.csv}",
             "P-4101", "--on", ON),
        case("existing:receipt:missing-file", "existing", "receipt", "{missing.csv}", "L-51001"),
        case("existing:receipt:no-category-column", "existing", "receipt", "{no-category-column.csv}", "L-1"),
        case("existing:notices:bad-date", "existing", "notices", "{bad-date.csv}", "{patrons.csv}", "--on", ON),
        case("existing:notices:none", "existing", "notices", "{no-fines.csv}", "{patrons.csv}", "--on", ON),
        case("existing:notices:unknown-patron", "existing", "notices", "{unknown-patron.csv}", "{patrons.csv}", "--on", ON),
        case("existing:account:no-fines", "existing", "account", "{no-fines.csv}", "{patrons.csv}", "P-4101", "--on", ON),
        case("existing:account:unknown-patron", "existing", "account", "{no-fines.csv}", "{patrons.csv}", "P-4999", "--on", ON),
        case("existing:account:block-at-ten", "existing", "account", "{block-at-ten.csv}", "{patrons.csv}", "P-4105",
             "--on", ON),
        case("existing:usage:none", "existing"),
        case("existing:usage:receipt-missing-id", "existing", "receipt", "{policy-loans.csv}"),
        case("existing:usage:bad-on", "existing", "notices", "{policy-loans.csv}", "{patrons.csv}", "--on", "2026-13-40"),
        case("existing:usage:account-missing-id", "existing", "account", "{policy-loans.csv}", "{patrons.csv}", "--on", ON),
        case("existing:usage:unknown-command", "existing", "fines", "{policy-loans.csv}"),
    ]
)

if __name__ == "__main__":
    doc = {"note": "Inputs only: expected output comes from reference.py at check time. Arguments {name} are the "
                   "files below, written to the case directory; a name not listed is a missing file.",
           "files": FILES, "cases": CASES}
    Path(__file__).with_name("cases.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
