"""Regenerate the hidden holds exports and cases for ts-extend-domain.

Run from anywhere: python3 make_cases.py (needs node 22.18+ or 23.6+). It writes data/ and cases.json next to itself.

Pull cases on valid exports get their expected output and status from reference.py (docs/pull.md over the fixture's
own catalog/callnumber.py); pull cases on exports that cannot be read or parsed, and every case of the existing
commands (holds, check), get theirs from running the fixture's own shelfwise. The generator then runs the qualify
reference (qualify/solutions/good) on every case and stops unless it agrees, and checks that each careless variant
the qualify README names gets some pull case wrong.

The exports draw call numbers from every form the scheme has (collections, Dewey numbers with and without fractions
and trailing zeros, Cutters whose digits order only as decimal fractions, names with apostrophes and hyphens, years,
volumes, copies, mixed case and spacing) and every mistake docs/callnumbers.md lists, put pairs that shelve together
in the export against hold-id order, and use only spaces and tabs as white space and ASCII digits, where Python and
JavaScript read text alike.
"""
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE.parent
FIXTURE = SCENARIO / "fixture"
GOOD = SCENARIO / "qualify" / "solutions" / "good"
DATA = HERE / "data"
sys.path.insert(0, str(HERE))
import reference  # noqa: E402

BRANCHES = ["Eastside", "Harbour", "Northgate", "Old Town", "Mill Lane"]
TITLES = ["The essentials of classic Italian cooking", "Butterflies of the world", "Soups, stews, and broths",
          'The "good" weekend', "On food and cooking", "A history of the world in 100 objects", "Atlas of remote islands",
          "Gödel, Escher, Bach", "Learning TypeScript", "The country girls", "Persepolis", "Wolf Hall",
          "Birds of the Atlantic coast", "Moomin and the comet", "The new joy of cooking", "Origami for beginners"]
WHOLE = ["000", "005", "030", "133", "595", "641", "741", "813", "912", "999"]
FRACTIONS = ["", ".1", ".10", ".133", ".5", ".50", ".502", ".59", ".5945", ".6", ".789"]
CUTTERS = ["S", "S6", "S60", "S637", "S64", "SM", "SMI", "R9", "A1", "AB12", "Q", "HAZ", "KIR", "M4", "M37"]
NAMES = ["OATES", "O'BRIEN", "OKAFOR", "SMITH-JONES", "SMITHERS", "SMITH", "D'ANGELO", "DANGELO", "MC-NAB", "MCNAB",
         "TAMAKI", "MANTEL", "JANSSON", "SATRAPI"]
COLLECTIONS = ["", "", "", "J", "YA", "REF", "OS"]
BAD = ["", "   ", "J", "YA  ", "64.5 ABC", "6415 ABC", "641. ABC", "641.5", "FIC", "B", "641.5 S6X", "641.5 SMIT",
       "641.5 6S", "B 0KEEFFE", "FIC -SMITH", "FIC MÜLLER", "XYZ 123", "AV 791.43 KUB", "FIC SMITH C.2 V.1",
       "FIC SMITH 1499", "FIC SMITH 2100", "FIC SMITH V.0", "FIC SMITH V.01", "030 WOR 2024 2025", "FIC SMITH extra",
       'FIC "SMITH"', "REF 030 WOR V.1000"]


ORDER_GROUPS = ["813 S64", "813 S637", "813 S6", "813 S", "813 SM", "641.5 M4", "641.5 M37", "641.5 M370",
                "641 A", "641.502 A", "641.59 A", "641.5945 A", "641.6 A",
                "FIC OKAFOR", "FIC O'BRIEN", "FIC OATES", "FIC SMITH-JONES", "FIC SMITHERS",
                "FIC ADAMS", "J 001 A", "B LINCOLN", "005 Z", "GN MOORE", "OS 700 B", "REF 030 WOR", "YA FIC GREEN",
                "030 WOR 2024 V.10", "030 WOR 2024 V.9", "030 WOR", "030 WOR 2019", "030 WOR 2024 V.9 C.2"]


def suffix(rng):
    parts = []
    if rng.random() < 0.3:
        parts.append(str(rng.choice([1998, 2005, 2019, 2021, 2024, 1500, 2099])))
    if rng.random() < 0.2:
        parts.append(f"V.{rng.choice([1, 2, 9, 10, 12, 100])}")
    if rng.random() < 0.15:
        parts.append(f"C.{rng.choice([1, 2, 3, 11])}")
    return parts


def good_callnumber(rng):
    coll = rng.choice(COLLECTIONS)
    if rng.random() < 0.6:
        words = [rng.choice(WHOLE) + rng.choice(FRACTIONS), rng.choice(CUTTERS)]
    else:
        words = [rng.choice(["B", "GN", "FIC", "FIC"]), rng.choice(NAMES)]
    words = ([coll] if coll else []) + words + suffix(rng)
    text = " ".join(words)
    r = rng.random()
    if r < 0.15:
        text = text.lower()
    elif r < 0.25:
        text = "  " + "   ".join(words) + " "
    elif r < 0.3:
        text = "\t".join(words)
    return text


def export(rng, n, first_id):
    rows, hid = [], first_id
    for _ in range(n):
        hid += rng.choice([1, 1, 2, 5])
        cn = rng.choice(BAD) if rng.random() < 0.08 else good_callnumber(rng)
        status = rng.choices(["waiting", "ready", "collected", "cancelled"], weights=[70, 10, 10, 10])[0]
        branch = rng.choices(BRANCHES, weights=[30, 25, 20, 15, 10])[0]
        rows.append([str(hid), branch, f"2026-09-{rng.randrange(1, 31):02d}", rng.choice(TITLES), cn, status])
    # Groups that each order rule of docs/callnumbers.md puts in a different order than a careless reading would.
    for branch in BRANCHES[:4]:
        for cn in ORDER_GROUPS:
            if rng.random() < 0.7:
                hid += rng.choice([1, 2])
                rows.append([str(hid), branch, "2026-09-20", rng.choice(TITLES), cn, "waiting"])
    # Pairs that shelve together, in the export against hold-id order (the second has the lower hold id, so it is
    # pulled first). Trailing zeros go both ways: a comparison of the digits as text, zeros kept, puts the shorter
    # first and is right only when the shorter has the lower hold id.
    for a, b in [("641.50 HAZ", "641.5 HAZ"), ("FIC D'ANGELO", "FIC DANGELO"), ("813 S60", "813 S6"),
                 ("B MC-NAB", "b mcnab"), ("J 595.789 KIR", "j  595.7890  kir"), ("813 S6", "813 S60"),
                 ("641.5 HAZ", "641.50 HAZ"), ("641.5 M37", "641.5 M370")]:
        for branch in ("Eastside", "Harbour"):
            hid += 3
            rows.append([str(hid + 1), branch, "2026-09-15", rng.choice(TITLES), a, "waiting"])
            rows.append([str(hid), branch, "2026-09-15", rng.choice(TITLES), b, "waiting"])
            hid += 1
    rng.shuffle(rows)
    return rows


def write_csv(name, rows, blank_lines=False, crlf=False):
    def field(v):
        return '"' + v.replace('"', '""') + '"' if any(c in v for c in ',"\n') else v
    lines = [",".join(reference.HEADER)]
    for i, r in enumerate(rows):
        lines.append(",".join(field(v) for v in r))
        if blank_lines and i % 23 == 22:
            lines.append("")
    end = "\r\n" if crlf else "\n"
    (DATA / name).write_text(end.join(lines) + end, encoding="utf-8")


def shelfwise(code, args, cwd):
    r = subprocess.run(["node", str(Path(code) / "bin" / "shelfwise.ts"), *args], cwd=cwd, capture_output=True,
                       text=True, env={"PATH": "/usr/bin:/bin", "NO_COLOR": "1", "NODE_NO_WARNINGS": "1"}, timeout=60)
    return r.returncode, r.stdout, r.stderr


def main():
    rng = random.Random(2026_10_05)
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir()
    write_csv("holds.csv", export(rng, 420, 5000), blank_lines=True)
    write_csv("crlf.csv", export(rng, 60, 9000), crlf=True)
    write_csv("one.csv", [["7001", "Eastside", "2026-09-01", "Persepolis", "GN SATRAPI", "waiting"],
                          ["7002", "Eastside", "2026-09-02", "Wolf Hall", "FIC MANTEL", "ready"],
                          ["7003", "Harbour", "2026-09-02", "Wolf Hall", "FIC MANTEL 2009", "cancelled"]])
    write_csv("allbad.csv", [[str(7100 + i), "Northgate", "2026-09-03", rng.choice(TITLES), cn, "waiting"]
                             for i, cn in enumerate(BAD)])
    write_csv("baddate.csv", [["7201", "Eastside", "2026-09-01", "Persepolis", "GN SATRAPI", "waiting"],
                              ["7202", "Eastside", "2026-09-02", "Wolf Hall", "FIC MANTEL", "waiting"],
                              ["7203", "Eastside", "2026-09-31", "Wolf Hall", "FIC MANTEL", "waiting"]])
    (DATA / "unterminated.csv").write_text(",".join(reference.HEADER) + '\n7301,Eastside,2026-09-01,"Open quote,FIC X,waiting\n',
                                           encoding="utf-8")
    (DATA / "short.csv").write_text(",".join(reference.HEADER) + "\n7401,Eastside,2026-09-01,Persepolis,GN SATRAPI\n",
                                    encoding="utf-8")

    pull_ok = [(f"pull-{b.lower().replace(' ', '-')}", ["pull", "--branch", b, "{data}/holds.csv"]) for b in BRANCHES]
    pull_ok += [
        ("pull-crlf", ["pull", "--branch", "Eastside", "{data}/crlf.csv"]),
        ("pull-one", ["pull", "--branch", "Eastside", "{data}/one.csv"]),
        ("pull-none-waiting", ["pull", "--branch", "Harbour", "{data}/one.csv"]),
        ("pull-unknown-branch", ["pull", "--branch", "Riverside", "{data}/holds.csv"]),
        ("pull-branch-case", ["pull", "--branch", "eastside", "{data}/holds.csv"]),
        ("pull-all-bad", ["pull", "--branch", "Northgate", "{data}/allbad.csv"]),
        ("pull-options-after", ["pull", "{data}/holds.csv", "--branch", "Mill Lane"]),
        ("pull-repo-sample", ["pull", "--branch", "Eastside", "test/data/holds.csv"]),
    ]
    pull_err = [
        ("pull-missing-file", ["pull", "--branch", "Eastside", "{data}/nope.csv"], "cannot read"),
        ("pull-bad-record", ["pull", "--branch", "Eastside", "{data}/baddate.csv"], "line 4: bad date '2026-09-31'"),
        ("pull-short-record", ["pull", "--branch", "Eastside", "{data}/short.csv"], "line 2: expected 6 fields, found 5"),
        ("pull-unterminated", ["pull", "--branch", "Eastside", "{data}/unterminated.csv"], "unterminated quoted field"),
        ("pull-no-branch", ["pull", "{data}/holds.csv"], ""),
        ("pull-two-files", ["pull", "--branch", "Eastside", "{data}/one.csv", "{data}/holds.csv"], ""),
        ("pull-unknown-option", ["pull", "--branch", "Eastside", "--sort", "title", "{data}/holds.csv"], ""),
    ]
    existing = [
        ("holds-eastside", ["holds", "--branch", "Eastside", "{data}/holds.csv"], ""),
        ("holds-old-town-waiting", ["holds", "--branch", "Old Town", "--status", "waiting", "{data}/holds.csv"], ""),
        ("holds-crlf", ["holds", "--branch", "Harbour", "{data}/crlf.csv"], ""),
        ("holds-bad", ["holds", "--branch", "Eastside", "{data}/baddate.csv"],
         "shelfwise holds: {data}/baddate.csv line 4: bad date '2026-09-31'"),
        ("check-holds", ["check", "{data}/holds.csv"], ""),
        ("check-bad", ["check", "{data}/baddate.csv"], ""),
        ("check-short", ["check", "{data}/short.csv"], ""),
        ("usage-unknown-command", ["frobnicate", "{data}/holds.csv"], "unknown command 'frobnicate'"),
    ]

    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__"))

        def expand(args):
            return [a.replace("{data}", str(DATA)) for a in args]

        for name, args in pull_ok:
            path = expand([a for a in args if "csv" in a])[0]
            branch = args[args.index("--branch") + 1]
            stdout, status = reference.pull(path if Path(path).is_absolute() else repo / path, branch)
            cases.append({"name": name, "kind": "pull", "args": args, "status": status, "stdout": stdout,
                          "repo_files": ["test/data/holds.csv"] if not args[-1].startswith("{data}") and "{data}" not in " ".join(args) else []})
        for name, args, fragment in pull_err:
            rc, out, err = shelfwise(repo, ["holds", *expand(args)[1:]] if fragment else expand(args), repo)
            status = 2
            if fragment:
                assert rc == 2 and fragment in err, (name, rc, err)
            cases.append({"name": name, "kind": "pull", "args": args, "status": status, "stdout": "",
                          "stderr_has": [fragment] if fragment else []})
        for name, args, fragment in existing:
            rc, out, err = shelfwise(repo, expand(args), repo)
            assert fragment.replace("{data}", str(DATA)) in err, (name, err)
            cases.append({"name": name, "kind": "existing", "args": args, "status": rc, "stdout": out,
                          "stderr_has": [fragment] if fragment else []})

        good = Path(tmp) / "good"
        shutil.copytree(repo, good)
        shutil.copytree(GOOD, good, dirs_exist_ok=True)

        def verify(code, label, only_pull=False):
            wrong = []
            for c in cases:
                if only_pull and c["kind"] != "pull":
                    continue
                rc, out, err = shelfwise(code, expand(c["args"]), code)
                ok = rc == c["status"] and out == c["stdout"] and all(
                    f.replace("{data}", str(DATA)) in err for f in c.get("stderr_has", []))
                if not ok:
                    wrong.append(c["name"])
            return wrong

        wrong = verify(good, "good")
        assert not wrong, f"the qualify reference disagrees on {wrong}"
        variants = {
            "cutter-digits-as-integers": ("    || cmp(digitsA.replace(/0+$/, ''), digitsB.replace(/0+$/, ''));",
                                          "    || cmp(Number(digitsA || 0), Number(digitsB || 0));"),
            "cutter-digits-as-text": ("    || cmp(digitsA.replace(/0+$/, ''), digitsB.replace(/0+$/, ''));",
                                      "    || cmp(digitsA, digitsB);"),
            "names-with-punctuation": ("if (kindA !== 0) return cmp(a.mark.replace(/['-]/g, ''), b.mark.replace(/['-]/g, ''));",
                                       "if (kindA !== 0) return cmp(a.mark, b.mark);"),
            "dewey-fraction-as-text": ("    || cmp(fracA.replace(/0+$/, ''), fracB.replace(/0+$/, ''))",
                                       "    || cmp(fracA, fracB)"),
            # Equal fractions (641.5, 641.50) ordered by their text instead of by hold id. Reading the fraction as a
            # floating-point number alone is right on every case.
            "dewey-ties-by-text": ("    || cmp(fracA.replace(/0+$/, ''), fracB.replace(/0+$/, ''))",
                                   "    || cmp(Number('0.' + (fracA || '0')), Number('0.' + (fracB || '0'))) || cmp(fracA, fracB)"),
            "split-on-spaces-only": ("  return text.toUpperCase().split(/\\s+/).filter(Boolean).join(' ');",
                                     "  return text.toUpperCase().split(/ +/).filter(Boolean).join(' ');"),
        }
        source = (GOOD / "src" / "callnumber.ts").read_text()
        floats = source.replace("    || cmp(fracA.replace(/0+$/, ''), fracB.replace(/0+$/, ''))",
                                "    || cmp(Number('0.' + (fracA || '0')), Number('0.' + (fracB || '0')))")
        assert floats != source
        (good / "src" / "callnumber.ts").write_text(floats)
        wrong = verify(good, "dewey-as-float", only_pull=True)
        assert not wrong, f"Dewey fractions read as floating-point numbers, a correct reading, fail {wrong}"
        for vname, (old, new) in variants.items():
            assert old in source, vname
            (good / "src" / "callnumber.ts").write_text(source.replace(old, new))
            wrong = verify(good, vname, only_pull=True)
            print(f"variant {vname}: {len(wrong)} pull cases wrong")
            assert wrong, f"no pull case tells {vname} apart"
        (good / "src" / "callnumber.ts").write_text(source)
        pull_src = (GOOD / "src" / "commands" / "pull.ts").read_text()
        old = "good.sort((a, b) => compare(a.cn, b.cn) || a.hold.id - b.hold.id);"
        assert old in pull_src
        (good / "src" / "commands" / "pull.ts").write_text(pull_src.replace(old, "good.sort((a, b) => compare(a.cn, b.cn));"))
        wrong = verify(good, "ties-in-export-order", only_pull=True)
        print(f"variant ties-in-export-order: {len(wrong)} pull cases wrong")
        assert wrong
    (HERE / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(cases)} cases: {sum(c['kind'] == 'pull' for c in cases)} pull, "
          f"{sum(c['kind'] == 'existing' for c in cases)} existing")


if __name__ == "__main__":
    main()
