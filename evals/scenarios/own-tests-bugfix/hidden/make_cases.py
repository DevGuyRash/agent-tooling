"""Write hidden/cases.json: hidden `invoicing show` and `invoicing month` cases with the right implementation's
results, and check that the wrong variants fail required cases and that the fixture's tests catch the regression
as expected.

    python3 hidden/make_cases.py          # rewrite cases.json and report what each variant fails
    python3 hidden/make_cases.py --check  # only compare with the stored cases.json
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import variants  # noqa: E402

FIXTURE = variants.FIXTURE
PREFIX = "invoicing: "


def inv(number, day, customer, *lines):
    return json.dumps({"number": number, "date": day, "customer": customer,
                       "lines": [{"description": d, "quantity": q, "unit_price": p, "vat_rate": r} for d, q, p, r in lines]},
                      indent=1)


THREE_FLYERS = inv("HP-2026-0141", "2026-09-30", "Northgate Community Kitchen",
                   ("A5 flyers, 500", "1", "1.99", "20"), ("A4 posters, 20", "1", "1.99", "20"),
                   ("Postcards, 100", "1", "1.99", "20"), ("Recipe booklets", "40", "2.35", "0"))
AGREE = inv("HP-2026-0142", "2026-09-30", "Riverside Library Friends",
            ("Banner, 2m", "1", "45.00", "20"), ("Eyelets", "8", "0.25", "20"), ("Books", "12", "6.50", "0"))
MIXED = inv("HP-2026-0143", "2026-09-29", "Ada's Bakery",
            ("Menus, laminated", "3", "4.99", "20"), ("Stickers", "2", "4.99", "20"), ("Leaflets", "1", "0.70", "5"),
            ("Leaflets", "1", "0.70", "5"), ("Leaflets", "1", "0.70", "5"), ("Cookbook proofs", "2", "11.00", "0"))
DISCOUNT = inv("HP-2026-0144", "2026-09-28", "Harbour Choir",
               ("Concert programmes", "150", "0.333", "20"), ("Tickets", "300", "0.0333", "20"),
               ("Member discount", "1", "-4.99", "20"), ("Posters", "6", "1.99", "20"))
ODD_RATES = inv("HP-2026-0145", "2026-09-27", "Old Town Heritage Trust",
                ("Design time, hours", "2.5", "30.00", "20"), ("Archive scans", "17", "0.85", "17.5"),
                ("Archive scans", "13", "0.85", "17.5"), ("Children's activity sheets", "7", "0.43", "5"),
                ("Leaflets, A6", "1", "2.50", "5"), ("Bookmarks", "3", "0.335", "0"))
PENNIES = inv("HP-2026-0146", "2026-09-26", "Seaview Allotments",
              *[(f"Seed packet labels, batch {n}", "1", "0.99", "20") for n in range(1, 13)])


def generated(seed, count):
    rng = random.Random(seed)
    customers = ["Northgate Community Kitchen", "Ada's Bakery", "Harbour Choir", "Riverside Library Friends",
                 "Seaview Allotments", "Old Town Heritage Trust", "Quayside Cycle Club"]
    out = {}
    for n in range(count):
        lines = []
        for _ in range(rng.randint(1, 7)):
            rate = rng.choice(["20", "20", "20", "5", "0"])
            price = f"{rng.randint(5, 2500) / 100:.2f}" if rng.random() < 0.7 else f"{rng.randint(50, 999) / 1000:.3f}"
            lines.append((rng.choice(["Flyers", "Posters", "Booklets", "Cards", "Banners", "Labels"]),
                          str(rng.choice([1, 1, 2, 3, 5, 10, 25, 100])), price, rate))
        number = f"HP-2026-{200 + n:04d}"
        out[f"sept/{number}.json"] = inv(number, f"2026-09-{rng.randint(1, 30):02d}", rng.choice(customers), *lines)
    return out


def case(name, files, args, required=True, stderr="exact"):
    return {"name": name, "files": files, "args": args, "required": required, "stderr_match": stderr}


CASES = [
    case("show-three-flyers", {"x.json": THREE_FLYERS}, ["show", "{dir}/x.json"]),
    case("show-agreeing", {"x.json": AGREE}, ["show", "{dir}/x.json"]),
    case("show-mixed-rates", {"x.json": MIXED}, ["show", "{dir}/x.json"]),
    case("show-discount-line", {"x.json": DISCOUNT}, ["show", "{dir}/x.json"]),
    case("show-odd-rates", {"x.json": ODD_RATES}, ["show", "{dir}/x.json"]),
    case("show-many-pennies", {"x.json": PENNIES}, ["show", "{dir}/x.json"]),
    case("month-small", {"sept/a.json": THREE_FLYERS, "sept/b.json": AGREE, "sept/c.json": MIXED,
                         "sept/d.json": DISCOUNT, "sept/e.json": ODD_RATES, "sept/f.json": PENNIES}, ["month", "{dir}/sept"]),
    case("month-agreeing", {"sept/b.json": AGREE}, ["month", "{dir}/sept"]),
    case("month-generated", generated(20261002, 40), ["month", "{dir}/sept"]),
    case("show-missing-file", {}, ["show", "{dir}/missing.json"], stderr="prefix"),
    case("show-bad-json", {"x.json": "{\"number\": "}, ["show", "{dir}/x.json"], stderr="prefix"),
    case("month-empty", {"sept/notes.txt": "nothing yet\n"}, ["month", "{dir}/sept"], stderr="prefix"),
]


def build(name, root):
    tree = Path(root) / name
    tree.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, tree, ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in variants.variant(name).items():
        (tree / rel).write_text(text, encoding="utf-8")
    return tree


def run_cases(tree, cases):
    results = []
    for c in cases:
        with tempfile.TemporaryDirectory() as d:
            for rel, text in c["files"].items():
                (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / rel).write_text(text, encoding="utf-8")
            args = [a.replace("{dir}", d) for a in c["args"]]
            p = subprocess.run([sys.executable, "-B", "-m", variants.PACKAGE, *args], cwd=tree, capture_output=True,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=60)
            results.append({"exit": p.returncode, "stdout": p.stdout.decode().replace(d, "{dir}"),
                            "stderr": p.stderr.decode().replace(d, "{dir}")})
    return results


def matches(result, expect, how):
    if result is None or result["exit"] != expect["exit"] or result["stdout"] != expect["stdout"]:
        return False
    if how == "prefix":
        return result["stderr"].startswith(PREFIX)
    return result["stderr"] == expect["stderr"]


def main():
    check_only = "--check" in sys.argv
    with tempfile.TemporaryDirectory() as root:
        right = run_cases(build("right", root), CASES)
        out = [dict(c, expect=r) for c, r in zip(CASES, right)]
        for c in out:
            if c["stderr_match"] == "prefix" and not (c["expect"]["exit"] == 1 and c["expect"]["stderr"].startswith(PREFIX)):
                raise SystemExit(f"{c['name']}: the right implementation does not fail with {PREFIX!r}")
        for name in variants.NAMES[1:]:
            got = run_cases(build(name, root), CASES)
            failed = [c["name"] for c, r in zip(out, got) if c["required"] and not matches(r, c["expect"], c["stderr_match"])]
            print(f"{name}: fails {len(failed)} required case(s): {', '.join(failed) or '-'}")
            if not failed:
                raise SystemExit(f"{name} passes every required case")
        for name in variants.NAMES:
            tree = build(name, Path(root) / "suite")
            p = subprocess.run([sys.executable, "-B", "-m", "unittest"], cwd=tree, capture_output=True, text=True)
            print(f"fixture tests with {name}: {p.stderr.strip().splitlines()[-1]}")
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
