"""Write hidden/cases.json: hidden `listings slug` and `listings build` cases with the right implementation's
results, and check that the wrong variants fail required cases and how the fixture's own tests fare with each.

    python3 hidden/make_cases.py          # rewrite cases.json and report what each variant fails
    python3 hidden/make_cases.py --check  # only compare with the stored cases.json
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import variants  # noqa: E402

FIXTURE = variants.FIXTURE
PREFIX = "listings: "

EVENTS = """title,venue,date,time
Café Müller,Dance Base,2026-08-15,19:00
Late Night Comedy,The Old Fish Market,2026-08-14,22:30
Cafe Muller,Studio 2,2026-08-15,21:30
Łódź Jazz Night,The Lighthouse,2026-08-15,21:00
Straße der Lieder,St Ninian's Church,2026-08-16,18:00
Strasse der Lieder,Quay Theatre,2026-08-17,18:00
Smørrebrød & Æbleskiver,Harbour Kitchen,2026-08-17,12:30
東京 Taiko,The Old Fish Market,2026-08-18,20:00
東京,Quay Theatre,2026-08-18,22:00
"""


def slug_case(name, titles, required=True):
    return {"name": name, "files": {}, "args": ["slug", *titles], "required": required, "stderr_match": "exact"}


CASES = [
    slug_case("accents", ["Café Müller", "Crème Brûlée Cookalong", "Año Nuevo Cumbia", "Ça va? Ñandú",
                          "Dvořák for Toddlers", "Šibenik Brass Band", "ÉCOLE DES FEMMES", "Tiếng Việt Poetry Slam"]),
    slug_case("spelled-letters", ["Łódź Jazz Night", "Straße der Lieder", "Smørrebrød Social", "Æsop's Fables",
                                  "Œdipus Rex", "Kraków Klezmer", "ØRESUND BLUES", "Hælp! A Musical"]),
    # Characters outside a-z between letters still separate words: a slug that drops them ("jazzblues-night") breaks
    # a rule the ticket keeps, as dropping everything that does not decompose to ASCII does.
    slug_case("unchanged-rules", ["Late Night Comedy", "  Jazz & Blues: LIVE!  ", "Hamlet (2026)", "a -- b __ c",
                                  "Rock'n'Roll Bingo", "!!! ***", "東京 Taiko", "東京", "Ελληνικά Night",
                                  "Хор Хорошо", "Jazz—Blues Night", "Rock×Roll", "Taiko東京Drums"]),
    slug_case("mixed", ["Fête de la Musique: Ü18 Rave", "São Paulo × Łódź", "Crêpes & Smørrebrød -- 2 för 1",
                        "Café–Bar Quiz"]),
    {"name": "build-collisions", "files": {"events.csv": EVENTS}, "args": ["build", "{dir}/events.csv", "{dir}/site"],
     "collect": "{dir}/site", "required": True, "stderr_match": "exact"},
    {"name": "build-bad-file", "files": {"events.csv": "title,venue,date\nX,Y,2026-08-14\n"},
     "args": ["build", "{dir}/events.csv", "{dir}/site"], "required": True, "stderr_match": "prefix"},
    # The ticket does not settle these: measures only.
    slug_case("not-settled", ["Đorđe's Quartet", "GROẞE NACHT", "ﬁnale", "İstanbul Nights"], required=False),
]


def build(name, root):
    tree = Path(root) / name
    tree.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, tree, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    for rel, text in variants.variant(name).items():
        (tree / rel).write_text(text, encoding="utf-8")
    return tree


def collect(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            found[os.path.relpath(path, root)] = Path(path).read_bytes().decode("utf-8", "replace")
    return found


def run_cases(tree, cases):
    results = []
    for c in cases:
        with tempfile.TemporaryDirectory() as d:
            for rel, text in c["files"].items():
                (Path(d) / rel).write_text(text, encoding="utf-8")
            args = [a.replace("{dir}", d) for a in c["args"]]
            p = subprocess.run([sys.executable, "-B", "-m", variants.PACKAGE, *args], cwd=tree, capture_output=True,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=60)
            result = {"exit": p.returncode, "stdout": p.stdout.decode().replace(d, "{dir}"),
                      "stderr": p.stderr.decode().replace(d, "{dir}")}
            if c.get("collect"):
                site = c["collect"].replace("{dir}", d)
                result["files"] = collect(site) if os.path.isdir(site) else None
            results.append(result)
    return results


def matches(result, case):
    expect = case["expect"]
    if result["exit"] != expect["exit"] or result["stdout"] != expect["stdout"]:
        return False
    if "files" in expect and result.get("files") != expect["files"]:
        return False
    if case["stderr_match"] == "prefix":
        return result["stderr"].startswith(PREFIX)
    return result["stderr"] == expect["stderr"]


def main():
    check_only = "--check" in sys.argv
    with tempfile.TemporaryDirectory() as root:
        right = run_cases(build("right", root), CASES)
        out = [dict(c, expect=r) for c, r in zip(CASES, right)]
        for name in variants.NAMES[1:]:
            got = run_cases(build(name, root), CASES)
            failed = [c["name"] for c, r in zip(out, got) if c["required"] and not matches(r, c)]
            print(f"{name}: fails {len(failed)} required case(s): {', '.join(failed) or '-'}")
            if not failed:
                raise SystemExit(f"{name} passes every required case")
        for name in variants.NAMES:
            tree = build(name, Path(root) / "suite")
            p = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=tree,
                               capture_output=True, text=True)
            print(f"fixture tests with {name}: {p.stdout.strip().splitlines()[-1]}")
    path = HERE / "cases.json"
    text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    if check_only:
        if path.read_text(encoding="utf-8") != text:
            raise SystemExit("cases.json differs from what the right implementation gives")
        print("cases.json matches")
    else:
        path.write_text(text, encoding="utf-8")
        print(f"wrote {len(out)} cases ({sum(c['required'] for c in out)} required)")


if __name__ == "__main__":
    main()
