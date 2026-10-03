"""Write hidden/cases.json: the renewals cases check.py runs, expected results from reference.py.

    python3 make_cases.py            rewrite cases.json, after checking the reference against rent.pl
    python3 make_cases.py --check    only compare: reference vs the fixture's tools/rent.pl on every valid
                                     case (needs perl), and the docs example vs the reference

A case's files are written to its own directory; "{dir}" in its arguments, its expected output, and its
expected error stands for that directory as the check passes it (a relative path).
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import reference

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
H = reference.HEADER + "\n"


def register(*rows, crlf=False):
    text = H + "".join(r + "\n" for r in rows)
    return text.replace("\n", "\r\n") if crlf else text


def generated(seed, n_plots, n_holders):
    rng = random.Random(seed)
    firsts = ["Ann", "Bilal", "Carys", "Dmitri", "Esther", "Femi", "Gwen", "Hamza", "Ines", "Jakub",
              "Kerry", "Lowri", "Mehmet", "Nell", "Oisin", "Pavla", "Rhys", "Sunita", "Tariq", "Una"]
    lasts = ["Ackroyd", "Bhatt", "Crowther", "Dlamini", "Evans", "Fenwick", "Gill", "Haworth", "Iqbal",
             "Jowett", "Kaur", "Lister", "Mensah", "Nuttall", "Oduya", "Pickles", "Quinn", "Rossi"]
    holders = sorted({f"{rng.choice(firsts)} {rng.choice(lasts)}" for _ in range(n_holders * 2)})[:n_holders]
    conc = {h: rng.random() < 0.3 for h in holders}
    rows, used = [], set()
    while len(rows) < n_plots:
        plot = f"{rng.choice('ABCDE')}{rng.randint(1, 140)}"
        if plot in used:
            continue
        used.add(plot)
        kind = rng.choices(["full", "half", "bed", "community"], [6, 4, 2, 1])[0]
        size = {"full": rng.randint(150, 420), "half": rng.randint(20, 150), "bed": rng.choice([6, 9, 12]),
                "community": rng.randint(200, 600)}[kind]
        if rng.random() < 0.12:
            rows.append(f"{plot},{size},{kind},,,,{rng.choice(['', 'Y', 'T'])}")
            continue
        holder = rng.choice(holders)
        y = rng.choice([2008, 2015, 2021, 2025, 2026, 2026, 2027, 2027])
        start = f"{y}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        rows.append(f"{plot},{size},{kind},{holder},{start},{'Y' if conc[holder] else ''},"
                    f"{rng.choice(['', 'Y', 'Y', 'T'])}")
    return register(*rows)


def big_holder():
    """One holder with many full plots, so a holder's own total passes £1,000."""
    rows = [f"D{i},{300 + i},full,Hollins Lane Allotment Society,2010-01-01,,Y" for i in range(1, 14)]
    rows += ["D20,9,bed,Una Quinn,2026-12-01,Y,"]
    return register(*rows)


CASES = [
    # (name, season args, register text or None for the default register, plots file name)
    ("fixture-2026", ["--season", "2026"], "FIXTURE", "plots.csv"),
    ("fixture-2025", ["--season", "2025"], "FIXTURE", "plots.csv"),
    ("fixture-2027-default-path", ["--season", "2027"], None, None),
    ("second-plots", ["--season", "2026"], register(
        "B4,250,full,Rhian Evans,2015-04-01,,Y",
        "A9,133,full,Rhian Evans,2016-04-01,,",
        "A12,125,half,Rhian Evans,2016-04-01,,T",
        "C3,133,full,Rhian Evans,2017-04-01,,Y",
        "C10,9,bed,Rhian Evans,2017-04-01,,",
        "A2,250,full,Joe Platt,2012-01-01,,Y",
        "B1,400,community,Joe Platt,2012-01-01,,T",
        "C1,250,full,Joe Platt,2018-01-01,,",
    ), "plots.csv"),
    ("lower-field-concession", ["--season", "2026"], register(
        "C1,127,full,Aled Price,2010-03-03,Y,Y",
        "C2,129,full,Bea Moss,2010-03-03,Y,",
        "C3,128,half,Cal Frost,2010-03-03,,T",
        "C4,90,half,Dee Rowe,2010-03-03,Y,T",
        "C5,500,community,Ash Grove Scouts,2010-03-03,Y,Y",
        "C6,9,bed,Eve Lund,2010-03-03,Y,Y",
    ), "plots.csv"),
    ("joining-part-way", ["--season", "2026"], register(
        "A1,250,full,Oct First,2026-10-01,,Y",
        "A2,250,full,Oct Last,2026-10-31,,Y",
        "A3,250,full,Nov First,2026-11-01,,Y",
        "A4,250,full,Feb Leap,2027-02-28,,",
        "A5,250,full,Sep Last,2027-09-30,,T",
        "A6,250,full,Next Season,2027-10-01,,Y",
        "A7,177,full,Mid Year,2027-04-15,Y,T",
        "A8,400,community,Late Garden,2027-06-01,,Y",
        "A9,125,half,Old Hand,1998-06-01,,",
        "B1,250,full,Mid Year,2027-04-16,Y,",
    ), "plots.csv"),
    ("minimums", ["--season", "2026"], register(
        "A1,10,half,Tiny Plot,2019-01-01,,",
        "A2,9,bed,Bed Concession,2019-01-01,Y,T",
        "A3,30,half,Late Small,2027-08-01,Y,",
        "A4,600,community,Free Garden,2019-01-01,,",
        "A5,31,half,Just Over,2019-01-01,,Y",
    ), "plots.csv"),
    ("one-holder-one-plot", ["--season", "2030"], register("E7,250,full,Solo Grower,2029-12-31,,Y"), "plots.csv"),
    ("header-only", ["--season", "2026"], register(), "plots.csv"),
    ("nothing-charged", ["--season", "2026"], register(
        "A1,250,full,,,,Y", "A2,125,half,,,,T", "A3,250,full,Far Future,2031-05-05,,Y"), "plots.csv"),
    ("out-of-order-crlf-spaces", ["--season", "2026"], register(
        "C2 , 250 , full ,  Zoë Ångström , 2020-02-02 , , Y ",
        "",
        "A10,125,half,Siân O'Hara,2020-02-02,Y,T",
        "A2,250,full, Zoë Ångström,2021-02-02,,",
        "   ",
        "B11,9,bed,Siân O'Hara,2026-12-24,,",
        crlf=True), "register.csv"),
    ("big-holder", ["--season", "2026"], big_holder(), "plots.csv"),
    ("generated-a", ["--season", "2026"], generated(11, 320, 90), "plots.csv"),
    ("generated-b", ["--season", "2027"], generated(12, 180, 40), "plots.csv"),
    # errors in the register: exit 1, message on standard error, nothing on standard output
    ("bad-size", ["--season", "2026"], register(
        "A1,250,full,Ann Briggs,2019-01-01,,Y", "A2,125,half,Bo Lee,2019-01-01,,", "A3,2x,half,Cy Moor,2019-01-01,,"),
     "plots.csv"),
    ("duplicate-plot", ["--season", "2026"], register(
        "B2,250,full,Ann Briggs,2019-01-01,,Y", "B3,125,half,Bo Lee,2019-01-01,,", "B2,125,half,Cy Moor,2019-01-01,,"),
     "plots.csv"),
    ("bad-header", ["--season", "2026"], "plot,size,kind,holder,start,concession,water\nA1,250,full,Ann,2019-01-01,,\n",
     "plots.csv"),
    ("bad-date", ["--season", "2026"], register("A1,250,full,Ann Briggs,2019-13-01,,Y"), "plots.csv"),
    ("bad-water", ["--season", "2026"], register("A1,250,full,Ann Briggs,2019-01-01,,y"), "plots.csv"),
    ("missing-file", ["--season", "2026"], "MISSING", "absent.csv"),
    # usage errors: exit 2
    ("no-season", [], register("A1,250,full,Ann Briggs,2019-01-01,,Y"), "plots.csv"),
    ("bad-season", ["--season", "26-27"], register("A1,250,full,Ann Briggs,2019-01-01,,Y"), "plots.csv"),
]


def build():
    fixture_register = (FIXTURE / "data" / "plots.csv").read_text(encoding="utf-8")
    out = []
    for name, season_args, text, fname in CASES:
        case = {"name": name, "files": {}, "args": ["renewals", *season_args]}
        if text is None:  # the repository's own register, through the default path
            path, data = "data/plots.csv", fixture_register.encode()
        elif text == "MISSING":
            path, data = f"{{dir}}/{fname}", None
            case["args"] += ["--plots", path]
        else:
            body = fixture_register if text == "FIXTURE" else text
            case["files"][fname] = body
            path, data = f"{{dir}}/{fname}", body.encode()
            case["args"] += ["--plots", path]
        if not season_args or not season_args[-1].split("=")[-1].isdigit() or len(season_args[-1].split("=")[-1]) != 4:
            case.update(status=2, stdout="", stderr_contains="")
        elif data is None:
            case.update(status=1, stdout="", stderr_contains=f"cannot read {path}")
        else:
            season = int(season_args[-1].split("=")[-1])
            try:
                case.update(status=0, stdout=reference.renewals(path, data, season), stderr_contains="")
            except reference.Refusal as r:
                case.update(status=r.status, stdout="", stderr_contains=r.message)
        out.append(case)
    return out


def check_against_perl(cases):
    """Every valid case: rent.pl's per-plot rent and water equal the reference's."""
    import tempfile
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            if case["status"] != 0:
                continue
            season = [a for a in case["args"] if a.isdigit() or a.startswith("--season=")][-1].split("=")[-1]
            if case["files"]:
                (fname, body), = case["files"].items()
                path = Path(tmp) / fname
                path.write_text(body, encoding="utf-8", newline="")
                data = body.encode()
            else:
                path = FIXTURE / "data" / "plots.csv"
                data = path.read_bytes()
            r = subprocess.run(["perl", str(FIXTURE / "tools" / "rent.pl"), "--season", season, str(path)],
                               capture_output=True, text=True)
            want = [f"{p}\t{h}\t{rent}\t{water}" for p, h, rent, water in
                    reference.charges(reference.parse(str(path), data), int(season))]
            got = r.stdout.splitlines()[1:-1]
            if r.returncode != 0 or got != want:
                bad += 1
                print(f"MISMATCH {case['name']}: rent.pl exit {r.returncode}\n  rent.pl: {got[:5]}\n  reference: {want[:5]}")
    return bad


def check_docs_example():
    doc = (FIXTURE / "docs" / "renewals.md").read_text(encoding="utf-8")
    shown = [l for l in doc.split("```")[3].splitlines()[2:] if l and l != "..."]
    full = reference.renewals("data/plots.csv", (FIXTURE / "data" / "plots.csv").read_bytes(), 2026).splitlines()
    missing = [l for l in shown if l not in full]
    if missing or shown[0] != full[0] or shown[-1] != full[-1]:
        print("docs/renewals.md example differs from the reference:", missing)
        return 1
    return 0


def main(argv):
    cases = build()
    problems = check_against_perl(cases) + check_docs_example()
    if problems:
        print(f"{problems} problem(s); cases.json not written")
        return 1
    print(f"reference agrees with rent.pl on {sum(c['status'] == 0 for c in cases)} valid cases; docs example ok")
    if "--check" not in argv:
        (HERE / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
