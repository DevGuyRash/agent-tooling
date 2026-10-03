"""Write hidden/cases.json: the cases check.py runs against the agent's loanbook.

    python3 make_cases.py

`due` cases take their expected output from the reference below, written from docs/due.md; `overdue`
cases take theirs from the fixture's own loanbook, run here, so they hold the existing command to what it
printed before the change. A case's data files are written to its own directory, passed with --data.
"""
import datetime
import json
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"


def read_csv(text):
    lines = text.strip("\n").split("\n")
    head = lines[0].split(",")
    return [dict(zip(head, l.split(","))) for l in lines[1:]]


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def due_reference(files, on, within):
    items = {r["item"]: r["name"] for r in read_csv(files["items.csv"])}
    members = {r["member"]: (r["name"], r["phone"]) for r in read_csv(files["members.csv"])}
    start = datetime.date.fromisoformat(on)
    end = start + datetime.timedelta(days=within)
    loans = [r for r in read_csv(files["loans.csv"])
             if not r["returned"] and start <= datetime.date.fromisoformat(r["due"]) <= end]
    if not loans:
        return f"Nothing due {start} to {end}\n"
    groups = {}
    for r in loans:
        groups.setdefault(r["member"], []).append(r)
    order = sorted(groups, key=lambda m: (min(r["due"] for r in groups[m]), members[m][0]))
    out = [f"Due {start} to {end}", ""]
    for m in order:
        out.append(f"{members[m][0]} ({members[m][1]})")
        for r in sorted(groups[m], key=lambda r: (r["due"], r["item"])):
            out.append(f"  {r['due']}  {items[r['item']]} ({r['item']})")
    out += ["", f"{plural(len(loans), 'loan')}, {plural(len(groups), 'member')}"]
    return "\n".join(out) + "\n"


def fixture_files():
    return {name: (FIXTURE / "data" / name).read_text(encoding="utf-8")
            for name in ("items.csv", "members.csv", "loans.csv")}


def generated(seed, n_loans):
    rng = random.Random(seed)
    items = [(f"{c}-{i:02d}", f"{c} thing {i}") for c in "ABCDEFGH" for i in range(1, 9)]
    names = ["Aled Morgan", "Bea Holt", "Cai Jenkins", "Dina Rahman", "Ed Fairley", "Fern Okafor", "Gus Berry",
             "Hana Sato", "Ivo Petrov", "Jess Long", "Kit Marsh", "Lena Vogt"]
    members = [(f"M{100 + i}", n, f"07700 900{400 + i}") for i, n in enumerate(names)]
    rng.shuffle(members)  # member ids out of name order, so ties must sort by name, not id
    loans = []
    for k in range(n_loans):
        out = datetime.date(2026, 10, 1) + datetime.timedelta(days=rng.randint(-20, 15))
        due = out + datetime.timedelta(days=rng.randint(3, 14))
        returned = "" if rng.random() < 0.7 else (out + datetime.timedelta(days=rng.randint(1, 10))).isoformat()
        loans.append(f"L{k + 1:04d},{rng.choice(items)[0]},{rng.choice(members)[0]},{out},{due},{returned}")
    return {"items.csv": "item,name\n" + "".join(f"{a},{b}\n" for a, b in items),
            "members.csv": "member,name,phone\n" + "".join(f"{a},{b},{c}\n" for a, b, c in members),
            "loans.csv": "loan,item,member,out,due,returned\n" + "".join(l + "\n" for l in loans)}


TIES = {
    "items.csv": "item,name\nA-01,Axe\nB-01,Bike pump\nC-01,Chainsaw\nZ-09,Zester\n",
    "members.csv": "member,name,phone\nM900,Abel Ames,07700 900901\nM100,Zoe Zane,07700 900902\nM500,Mo Mills,07700 900903\n",
    "loans.csv": ("loan,item,member,out,due,returned\n"
                  "L1,Z-09,M100,2026-10-01,2026-10-11,\n"
                  "L2,A-01,M900,2026-10-01,2026-10-11,\n"
                  "L3,C-01,M100,2026-10-01,2026-10-12,\n"
                  "L4,B-01,M100,2026-10-01,2026-10-11,\n"
                  "L5,A-01,M500,2026-10-01,2026-10-10,2026-10-09\n"
                  "L6,C-01,M500,2026-10-01,2026-10-09,\n"),
}

SINGLE = {
    "items.csv": "item,name\nK-01,Kayak\n",
    "members.csv": "member,name,phone\nM001,Una Vale,07700 900001\n",
    "loans.csv": "loan,item,member,out,due,returned\nL1,K-01,M001,2026-12-20,2026-12-31,\n",
}


def cases():
    fx = fixture_files()
    due = [
        ("docs-example", fx, ["--on", "2026-10-05"]),
        ("within-1", fx, ["--on", "2026-10-05", "--within", "1"]),
        ("within-14", fx, ["--on", "2026-09-25", "--within", "14"]),
        ("returned-and-overdue-left-out", fx, ["--on", "2026-10-04", "--within", "3"]),
        ("nothing-due", fx, ["--on", "2026-11-01"]),
        ("ties-by-name-not-id", TIES, ["--on", "2026-10-10", "--within", "2"]),
        ("boundary-day-included", TIES, ["--on", "2026-10-09", "--within", "3"]),
        ("one-loan-one-member", SINGLE, ["--on", "2026-12-30", "--within", "2"]),
        ("year-end", SINGLE, ["--on", "2026-12-29", "--within", "1"]),
        ("generated-a", generated(7, 90), ["--on", "2026-10-06", "--within", "4"]),
        ("generated-b", generated(8, 140), ["--on", "2026-10-01", "--within", "14"]),
    ]
    out = []
    for name, files, args in due:
        on = args[args.index("--on") + 1]
        within = int(args[args.index("--within") + 1]) if "--within" in args else 2
        out.append({"name": f"due-{name}", "files": files, "args": ["due", *args], "status": 0,
                    "stdout": due_reference(files, on, within)})
    for name, args in [("within-0", ["--on", "2026-10-05", "--within", "0"]),
                       ("within-15", ["--on", "2026-10-05", "--within", "15"]),
                       ("bad-date", ["--on", "05/10/2026"])]:
        out.append({"name": f"due-{name}", "files": fx, "args": ["due", *args], "status": 2, "stdout": None})
    for name, files, args in [("docs", fx, ["--on", "2026-10-05"]), ("nothing", fx, ["--on", "2026-09-01"]),
                              ("ties", TIES, ["--on", "2026-10-13"]), ("generated", generated(9, 120), ["--on", "2026-10-08"])]:
        out.append({"name": f"overdue-{name}", "files": files, "args": ["overdue", *args], "existing": True})
    return out


def fill_existing(data):
    """Expected results for the existing command, from the fixture's own loanbook."""
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(FIXTURE, repo)
        for i, case in enumerate(data):
            if not case.get("existing"):
                continue
            d = repo / "cases" / f"{i:03d}"
            d.mkdir(parents=True)
            for fname, body in case["files"].items():
                (d / fname).write_text(body, encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "loanbook", "--data", f"cases/{i:03d}", *case["args"]],
                               cwd=repo, capture_output=True, text=True)
            case["status"], case["stdout"] = r.returncode, r.stdout
            del case["existing"]


def check_docs_example(data):
    doc = (FIXTURE / "docs" / "due.md").read_text(encoding="utf-8")
    block = doc.split("```")[3].strip("\n").split("\n")
    expected = "\n".join(block[1:]) + "\n"
    got = next(c for c in data if c["name"] == "due-docs-example")["stdout"]
    if got != expected:
        sys.exit("docs/due.md example differs from the reference")


if __name__ == "__main__":
    data = cases()
    fill_existing(data)
    check_docs_example(data)
    (HERE / "cases.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(data)} cases")
