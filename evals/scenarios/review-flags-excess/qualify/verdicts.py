"""Compares a finished run of a qualification plan with what every reference should get.

    python3 qualify/verdicts.py RUN_DIR [--repeats N] [--table]

Which plan the run is of is read from its plan.json. With a judge (qualify/judge-claude.json, qualify/judge-codex.json) it
is expected to hold every review reference, `empty`, and `noop`, three times each; without one
(evals/plans/qualify-review-flags-excess.json) every reference, the behaviors included, twice each. `--repeats` says
another number. It exits 1, naming each, when
- an expected arm or repeat is missing, or the run holds an arm or a repeat that is not expected;
- a run did not end ok, or its verdict (`passed`) is not the expected one: with a judge, the review written, the code
  unchanged, and the judge's verdict pass; without one, none, since a scenario that asks a judge question and has no judge
  is judge-missing and only its check values count;
- a check value is not the expected one (the required checks, the pattern measures, `extra_files`), in any repeat;
- with a judge, a run has no verdict, was judged by another judge than the others, or has a verdict other than the expected
  one (pass for every review but the ones in read_reviews.FAILS, fail for `empty` and `noop`).
With --table it prints the markdown rows of qualify/README.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a run leaves no bytecode caches in the repository
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_reviews  # noqa: E402

REQUIRED = ["review_written", "code_unchanged"]
REPEATS = {"checks": 2, "judge": 3}
# arms that are not just a review file: (the review they write, the code_unchanged they should get, extra_files)
BEHAVIOR = {
    "edits-code": ("good", False, "-"), "commits-code": ("good", False, "-"), "adds-test": ("good", False, "tests/test_ties.py"),
    "moves-branch": ("good", False, "-"), "commits-review": ("good", True, "-"), "switches-branch": ("good", True, "-"),
    "runs-tests": ("good", True, "out/M-1.txt"), "scratch-file": ("good", True, "repro.py"),
    "empty": (None, True, "-"), "noop": (None, True, "-"),
}


def expected_arms(judged):
    """The arms a run of the plan should hold: the review references, `empty`, and `noop`, and without a judge the
    behaviors that change the repository too (the judge reads a review, and these write `good`)."""
    arms = set(read_reviews.REVIEWS) | {"empty", "noop"}
    return arms if judged else arms | set(BEHAVIOR)


def verdict_of(arm):
    """What the judge question should answer for an arm."""
    review = BEHAVIOR.get(arm, (arm,))[0]
    return "fail" if review is None or review in read_reviews.FAILS else "pass"


def expected(arm, judged):
    """The check values and the run verdict an arm should get."""
    review, unchanged, extra = BEHAVIOR.get(arm, (arm, True, "-"))
    excess, decoys = read_reviews.REVIEWS[review] if review else ("", "")
    checks = {
        "review_written": review is not None, "code_unchanged": unchanged,
        "excess_reported": len(excess), "excess_registry_reported": "R" in excess, "excess_rounding_reported": "O" in excess,
        "excess_cache_reported": "C" in excess, "decoy_retry_flagged": "T" in decoys, "decoy_format_flagged": "F" in decoys,
        "extra_files": extra,
        **({"asks_to_add": read_reviews.ASKS[review][0], "asks_to_remove": read_reviews.ASKS[review][1]}
           if review in read_reviews.ASKS else {}),
    }
    return checks, (all(checks[name] for name in REQUIRED) and verdict_of(arm) == "pass") if judged else None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run", type=Path)
    ap.add_argument("--repeats", type=int, help="how many repeats of each arm the run should hold (default: 3 with a judge, 2 without)")
    ap.add_argument("--table", action="store_true", help="print the markdown rows of qualify/README.md")
    args = ap.parse_args(argv)
    run = args.run.expanduser()
    plan = json.loads((run / "plan.json").read_text(encoding="utf-8"))
    judged = bool(plan.get("judge"))
    repeats = args.repeats or REPEATS["judge" if judged else "checks"]
    results = {}
    for path in sorted(run.glob("runs/*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        results.setdefault(result["arm"], {})[result.get("repeat")] = result
    problems, lines, judges = [], [], set()
    want_arms = expected_arms(judged)
    for arm in sorted(want_arms | set(results)):
        if arm not in want_arms:
            problems.append("%s: not an arm this plan should hold" % arm)
            continue
        want, passed = expected(arm, judged)
        for number in range(1, repeats + 1):
            result = results.get(arm, {}).get(number)
            if result is None:
                problems.append("%s r%d: missing" % (arm, number))
                continue
            checks, found = result.get("checks", {}), []
            if result.get("status") != "ok":
                found.append("status %s" % result.get("status"))
            for name, value in want.items():
                if checks.get(name) != value:
                    found.append("%s is %r, wanted %r" % (name, checks.get(name), value))
            if result.get("passed") is not passed:
                found.append("verdict %r, wanted %r" % (result.get("passed"), passed))
            if judged:
                verdict = (result.get("judge") or {}).get("verdict")
                judges.add(json.dumps(result.get("judge_identity"), sort_keys=True))
                if verdict != verdict_of(arm):
                    found.append("judge said %r, wanted %r" % (verdict, verdict_of(arm)))
                if result.get("judge_missing") or result.get("judge_stale"):
                    found.append("judge-missing or judge-stale")
            elif not result.get("judge_missing"):
                found.append("not judge-missing, though the plan has no judge")
            if found:
                problems.append("%s r%d: %s" % (arm, number, "; ".join(found)))
            elif number == 1:
                failed = [name for name in REQUIRED if want[name] is not True] + (["judge"] if judged and verdict_of(arm) != "pass" else [])
                lines.append((arm, passed, failed, checks))
        for number in sorted(n for n in results.get(arm, {}) if n not in range(1, repeats + 1)):
            problems.append("%s r%s: not a repeat this plan should hold" % (arm, number))
    if judged and len(judges) > 1:
        problems.append("the runs were judged by %d judges, not one" % len(judges))
    for problem in problems:
        print("WRONG  " + problem)
    for arm, passed, failed, checks in lines:
        if args.table:
            print("| `%s` | %s | %s | %s | %s | %s |" % (arm, "pass" if passed else "fail", ", ".join("`%s`" % f for f in failed) or "none",
                                                          checks["excess_reported"], checks["asks_to_add"], checks["asks_to_remove"]))
        else:
            print("%-28s %-4s excess=%s asks add=%-2s remove=%-2s failed: %s" % (
                arm, "pass" if passed else ("fail" if passed is False else "-"), checks["excess_reported"], checks["asks_to_add"],
                checks["asks_to_remove"], ", ".join(failed) or "-"))
    held = sum(len(v) for v in results.values())
    print("%d arms expected, %d runs found, %d repeat(s) each expected, %d deviation(s)%s" % (
        len(want_arms), held, repeats, len(problems), " (judge: %s)" % plan["judge"].get("model") if judged else " (no judge)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
