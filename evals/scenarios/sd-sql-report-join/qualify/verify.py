"""Compare a qualification run with qualify/expected.json: for every arm and repeat, the run is valid,
passes exactly when no required check is expected to fail, fails exactly the expected required checks,
and has the expected measure values.

    python3 verify.py RUN_DIR
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(run_dir):
    required = json.loads((HERE.parent / "scenario.json").read_text())["required"]
    expected = json.loads((HERE / "expected.json").read_text())
    runs = defaultdict(list)
    for p in sorted(Path(run_dir).glob("runs/*/result.json")):
        r = json.loads(p.read_text())
        runs[r["arm"]].append(r)
    problems = []
    for arm in sorted(set(expected) | set(runs)):
        exp, got = expected.get(arm), runs.get(arm, [])
        if exp is None or not got:
            problems.append(f"{arm}: {'no expectation' if exp is None else 'no runs'}")
            continue
        for r in got:
            where = f"{arm} r{r['repeat']}"
            if r["status"] != "ok" or r["passed"] is None:
                problems.append(f"{where}: invalid ({r['status']}, {r.get('checks', {}).get('check_error', '')})")
                continue
            failing = sorted(k for k in required if r["checks"].get(k) is not True)
            if failing != sorted(exp["fail"]):
                problems.append(f"{where}: fails {failing}, expected {sorted(exp['fail'])}")
            if r["passed"] != (not exp["fail"]):
                problems.append(f"{where}: passed={r['passed']}")
            for k, v in exp.get("measures", {}).items():
                if r["checks"].get(k) != v:
                    problems.append(f"{where}: {k}={r['checks'].get(k)!r}, expected {v!r}")
        verdicts = {(r["passed"], tuple(sorted(k for k in required if r["checks"].get(k) is not True))) for r in got}
        print(f"{arm:<28} {sum(bool(r['passed']) for r in got)}/{len(got)} passed, "
              f"{len(verdicts)} distinct verdict(s), expected {'pass' if not exp['fail'] else 'fail'}")
    print("\n".join(problems) if problems else "all runs match qualify/expected.json")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
