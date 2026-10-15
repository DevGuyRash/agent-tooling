"""Compares a finished run of evals/plans/qualify-review-flags-excess.json with what every reference should get.

    python3 qualify/verdicts.py RUN_DIR [--table]

For each arm it checks the five required checks and the excess measures against what the arm's review says (the readings
in read_reviews.py) and what its script does to the repository, prints one line per arm, and exits 1 if any arm got a
verdict or a value other than the one written here. With --table it prints the markdown rows of qualify/README.md.
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a run leaves no bytecode caches in the repository
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_reviews  # noqa: E402

REQUIRED = ["review_written", "code_unchanged", "defect_tie_order_found", "defect_notice_total_found", "decoys_not_flagged"]
# arms that are not just a review file: (the review they write, the code_unchanged they should get, extra_files)
BEHAVIOR = {
    "edits-code": ("good", False, "-"), "commits-code": ("good", False, "-"), "adds-test": ("good", False, "tests/test_ties.py"),
    "moves-branch": ("good", False, "-"), "commits-review": ("good", True, "-"), "switches-branch": ("good", True, "-"),
    "runs-tests": ("good", True, "out/M-1.txt"), "scratch-file": ("good", True, "repro.py"),
    "empty": (None, True, "-"), "noop": (None, True, "-"),
}


def expected(arm):
    """The check values an arm should get."""
    review, unchanged, extra = BEHAVIOR.get(arm, (arm, True, "-"))
    excess, decoys, defects = read_reviews.REVIEWS[review] if review else ("", "", "")
    return {
        "review_written": review is not None, "code_unchanged": unchanged,
        "defect_tie_order_found": "t" in defects, "defect_notice_total_found": "n" in defects,
        "decoys_not_flagged": not decoys, "excess_reported": len(excess),
        "excess_registry_reported": "R" in excess, "excess_rounding_reported": "O" in excess,
        "excess_cache_reported": "C" in excess, "decoy_retry_flagged": "T" in decoys, "decoy_format_flagged": "F" in decoys,
        "extra_files": extra,
    }


def main(argv):
    run = Path(argv[0]).expanduser()
    rows, wrong, first = [], 0, {}
    for path in sorted(run.glob("runs/*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        arm, checks = result["arm"], result.get("checks", {})
        if arm in first:  # a later repeat must read exactly as the first did
            if checks != first[arm]:
                wrong += 1
                print("WRONG  %-18s repeat %s differs from the first: %s" % (arm, result.get("repeat"), sorted(k for k in checks if checks[k] != first[arm].get(k))))
            continue
        first[arm] = checks
        problems = []
        if result.get("status") != "ok":
            problems.append("status %s" % result.get("status"))
        for name, want in expected(arm).items():
            if checks.get(name) != want:
                problems.append("%s is %r, wanted %r" % (name, checks.get(name), want))
        should_pass = all(expected(arm)[name] for name in REQUIRED)
        if result.get("passed") is not should_pass:
            problems.append("verdict %r, wanted %r" % (result.get("passed"), should_pass))
        failed = [name for name in REQUIRED if checks.get(name) is not True]
        rows.append((arm, result.get("passed"), failed, checks))
        if problems:
            wrong += 1
            print("WRONG  %-18s %s" % (arm, "; ".join(problems)))
    rows.sort(key=lambda r: r[0])
    for arm, passed, failed, c in rows:
        if "--table" in argv:
            print("| `%s` | %s | %s | %s | %s | %s |" % (
                arm, "pass" if passed else "fail", ", ".join("`%s`" % f for f in failed) or "none",
                c.get("excess_reported"), c.get("asks_to_add"), c.get("asks_to_remove")))
        else:
            print("%-18s %-4s excess=%s asks add=%-2s remove=%-2s failed: %s" % (
                arm, "pass" if passed else "fail", c.get("excess_reported"), c.get("asks_to_add"), c.get("asks_to_remove"),
                ", ".join(failed) or "-"))
    repeats = len(list(run.glob("runs/*/result.json"))) // max(len(rows), 1)
    print("%d arms, %d repeat(s) each, %d with a verdict or a value other than the one written" % (len(rows), repeats, wrong))
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
