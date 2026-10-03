"""Write hidden/cases.json: the hidden `shiftboard week` cases with the right implementation's results, and check
that each wrong variant fails required cases and that the doc's example is what the right implementation prints.

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
SAMPLE = (FIXTURE / "docs/examples/roster-sample.csv").read_text(encoding="utf-8")
HEAD = "date,start,end,station,volunteer\n"

WIDE = HEAD + """2026-10-05,09:00,12:00,Prep,欧阳娜娜
2026-10-05,09:00,12:00,Serving,Bo Li
2026-10-05,12:00,15:00,Dish pit,田中 さくら
2026-10-06,17:00,20:00,Serving,이서연
2026-10-07,10:00,13:30,Delivery,Ana María Pérez
2026-10-08,09:00,12:00,Front desk,スズキ ハルト
2026-10-09,17:00,20:00,Prep,司马相如
2026-10-11,11:00,14:00,Serving,Ng
2026-10-12,09:00,12:00,Prep,Outside The Week
"""

FULLWIDTH = HEAD + """2026-10-13,08:00,11:00,配送センター,ＡＢＣ Catering
2026-10-13,08:00,11:00,Prep,ｶﾀｵｶ ﾘｮｳ
2026-10-14,17:30,21:00,Serving,Ｍｉｎｈ Ａｎｈ
2026-10-15,09:00,12:00,Prep,Noor
"""

AMBIGUOUS = HEAD + """2026-11-02,09:00,12:00,Prep,Ελένη Παπαδοπούλου
2026-11-02,09:00,12:00,Serving,Мария Иванова
2026-11-03,17:00,20:00,Serving,Zoë Ångström
2026-11-04,10:00,13:00,Delivery,Łukasz Żółć
2026-11-05,09:00,12:00,Dish pit,刘洋
"""

ORDER = HEAD + """2026-09-20,11:00,14:00,Serving,Late Sunday
2026-09-16,17:00,20:00,Serving,김민준
2026-09-14,12:00,15:00,Dish pit,Second At Noon
2026-09-14,09:00,12:00,Serving,First Of Two
2026-09-14,09:00,12:00,Prep,Second Of Two
2026-09-13,09:00,12:00,Prep,Sunday Before
2026-09-16,08:00,10:00,Prep,宋佳
2026-09-21,09:00,12:00,Prep,Monday After
2026-09-14,06:30,09:00,Delivery,Early Bird
"""

YEAR_END = HEAD + """2026-12-27,10:00,13:00,Serving,Sunday Before
2026-12-28,10:00,13:00,Serving,黄婷婷
2026-12-31,18:00,23:30,Serving,New Year Eve Crew
2027-01-01,12:00,15:00,Prep,Kai
2027-01-03,09:00,12:00,Front desk,박지훈
2027-01-04,09:00,12:00,Prep,Next Year Week One
"""

YEAR_START = HEAD + """2025-12-28,10:00,13:00,Serving,Sunday Before
2025-12-29,10:00,13:00,Serving,赵敏
2026-01-01,12:00,15:00,Prep,New Year Day
2026-01-04,09:00,12:00,Front desk,Ilse
2026-01-05,09:00,12:00,Prep,Week Two
"""

BAD_ROSTER = HEAD + "2026-09-14,09:00,12:00,Prep,Amara Okafor\n2026-09-15,9:00,12:00,Prep,Tomasz Nowak\n"


def case(name, files, args, required=True, stderr="exact"):
    return {"name": name, "files": files, "args": ["week", *args], "required": required, "stderr_match": stderr}


CASES = [
    case("doc-example", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W38"]),
    case("sample-w37", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W37"]),
    case("sample-w39", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W39"]),
    case("wide-names", {"r.csv": WIDE}, ["{dir}/r.csv", "2026-W41"]),
    case("fullwidth-and-halfwidth", {"r.csv": FULLWIDTH}, ["{dir}/r.csv", "2026-W42"]),
    case("ambiguous-width", {"r.csv": AMBIGUOUS}, ["{dir}/r.csv", "2026-W45"]),
    case("order-and-ties", {"r.csv": ORDER}, ["{dir}/r.csv", "2026-W38"]),
    case("year-end-w53", {"r.csv": YEAR_END}, ["{dir}/r.csv", "2026-W53"]),
    case("next-year-w01", {"r.csv": YEAR_END}, ["{dir}/r.csv", "2027-W01"]),
    case("year-start-w01", {"r.csv": YEAR_START}, ["{dir}/r.csv", "2026-W01"]),
    case("empty-week", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W40"]),
    case("bad-week-no-w", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-38"]),
    case("bad-week-54", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W54"]),
    case("bad-week-2025-w53", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2025-W53"]),
    case("bad-week-00", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W00"]),
    case("bad-week-words", {"r.csv": SAMPLE}, ["{dir}/r.csv", "week 38"]),
    case("bad-week-before-roster", {}, ["{dir}/missing.csv", "2026-W99"]),
    case("roster-error", {"bad.csv": BAD_ROSTER}, ["{dir}/bad.csv", "2026-W38"], stderr="prefix"),
    case("roster-missing", {}, ["{dir}/missing.csv", "2026-W38"], stderr="prefix"),
    # Forms docs/board.md settles less plainly: measures only.
    case("bad-week-one-digit", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-W5"], required=False),
    case("bad-week-lowercase", {"r.csv": SAMPLE}, ["{dir}/r.csv", "2026-w38"], required=False),
]
PREFIX = "shiftboard: "


def build(name, root):
    """A copy of the fixture with one variant's package, under root."""
    tree = Path(root) / name
    shutil.copytree(FIXTURE, tree, ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in variants.variant(name).items():
        (tree / rel).write_text(text, encoding="utf-8")
    return tree


def run_cases(tree, cases):
    results = []
    for c in cases:
        with tempfile.TemporaryDirectory() as d:
            for rel, text in c["files"].items():
                (Path(d) / rel).write_text(text, encoding="utf-8")
            args = [a.replace("{dir}", d) for a in c["args"]]
            p = subprocess.run([sys.executable, "-B", "-m", variants.PACKAGE, *args], cwd=tree, capture_output=True,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=30)
            results.append({"exit": p.returncode, "stdout": p.stdout.decode().replace(d, "{dir}"),
                            "stderr": p.stderr.decode().replace(d, "{dir}")})
    return results


def matches(result, expect, how):
    if result is None or result["exit"] != expect["exit"] or result["stdout"] != expect["stdout"]:
        return False
    if how == "prefix":
        return result["stderr"].startswith(PREFIX) and bool(result["stderr"].strip())
    return result["stderr"] == expect["stderr"]


def main():
    check_only = "--check" in sys.argv
    with tempfile.TemporaryDirectory() as root:
        right = run_cases(build("right", root), CASES)
        doc_example = (FIXTURE / "docs/examples/week-2026-W38.txt").read_text(encoding="utf-8")
        if right[0]["stdout"] != doc_example or right[0]["exit"] != 0:
            raise SystemExit("docs/examples/week-2026-W38.txt is not what the right implementation prints")
        if "```\n" + doc_example + "```" not in (FIXTURE / "docs/board.md").read_text(encoding="utf-8"):
            raise SystemExit("docs/board.md's example is not docs/examples/week-2026-W38.txt")
        out = [dict(c, expect=r) for c, r in zip(CASES, right)]
        for c in out:
            if c["stderr_match"] == "prefix" and not c["expect"]["stderr"].startswith(PREFIX):
                raise SystemExit(f"{c['name']}: the right implementation's error does not start with {PREFIX!r}")
        for name in variants.NAMES[1:]:
            got = run_cases(build(name, root), CASES)
            failed = [c["name"] for c, r in zip(out, got) if c["required"] and not matches(r, c["expect"], c["stderr_match"])]
            print(f"{name}: fails {len(failed)} required case(s): {', '.join(failed) or '-'}")
            if not failed:
                raise SystemExit(f"{name} passes every required case")
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
