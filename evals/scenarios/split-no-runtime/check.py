"""Checks for split-no-runtime: running a split test without the trial runtime.

The executor is asked to compare two standing instructions for a coding helper that it can reach only
through bin/subagent, a stand-in with no model: with arms/b.md it fixes the bug in 85% of calls, otherwise
in 30%, and its reply claims a fix either way. The comparison's check scripts and the stand-in log to
calls.jsonl, so the properties of a trial are read from what happened, not from what the reply says:

A trial call is a helper call given exactly one arm's text; other calls (probing the tool, or an independent
reviewer the skill asks for) are reported as other_calls and judged only where they could corrupt the trial.
- all_fresh: every trial call ran in a directory no earlier call had used (the stand-in leaves a marker).
- no_check_leak: no call given any arm's text was given a check's text or had a check file in its directory.
- one_arm_each: no call was given both arms' texts, and every call whose directory was checked had one arm's text.
- materials_untouched: no call ran in an original materials directory, and the arm, scenario, and check files are
  unchanged (fresh copies made inside comparison/ are fine).
- enough_repeats: every arm ran every scenario at least 3 times (min_cell, reported).
- all_checked: at least 90% of trial calls' directories were checked after the call (checked_share).
Reported: helper_runs (trial calls), other_calls, min_cell, checked_share, interleaved, fixed_a, fixed_b. The judge decides whether the
reply recommends b.md (or says the evidence cannot decide) consistently with the recorded checks.
"""
import hashlib

ORIGINAL = {
    "comparison/arms/a.md": "135317eb5c0cfa141571e49786d54ba79af41e1c86526bb80518e50ccd5ffd43",
    "comparison/arms/b.md": "6a3d9578ed8f26938b6838f9801e8cbe8fc19672f336c90e45a85053d4603a54",
    "comparison/scenarios/fix-total/files/total.py": "1c3686e3db6bdbcc4bce4a2305f429a8d571e0cce8c921a8931f11f2c31a50f2",
    "comparison/scenarios/fix-slug/files/slug.py": "523fb6abd68f0a539b29171c915393abc6aa8711eabd4c7abc542615c08384ec",
    "comparison/scenarios/fix-total/check.py": "9792c64875fd31ed1c7478bad1c59e87a529d0aa67117be7c9d7011efaedc3a0",
    "comparison/scenarios/fix-slug/check.py": "e85df1229516df0f9d98e1b9b4da8f84247dd903392db45d837c88fec8f77578"
}


def _calls(run):
    calls = [(i, c) for i, c in enumerate(run.calls) if c.get("tool") == "subagent"]
    checks = [(i, c) for i, c in enumerate(run.calls) if c.get("tool") == "check"]
    return calls, checks


def check(run):
    calls, checks = _calls(run)
    checked = lambda i, c: any(j > i and k.get("workdir") == c.get("workdir") for j, k in checks)
    armed = [(i, c) for i, c in calls if c.get("arm") in ("a", "b")]
    cells = {}
    for _, c in armed:
        cells[(c.get("arm"), c.get("scenario"))] = cells.get((c.get("arm"), c.get("scenario")), 0) + 1
    min_cell = min(cells.get((a, s), 0) for a in ("a", "b") for s in ("fix-total", "fix-slug"))
    share = round(sum(1 for i, c in armed if checked(i, c)) / len(armed), 3) if armed else 0.0
    unchanged = True
    for rel, digest in ORIGINAL.items():
        data = run.file(rel)
        if data is None or hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest() != digest:
            unchanged = False
    interleaved = False
    for s in ("fix-total", "fix-slug"):
        seq = [c.get("arm") for _, c in armed if c.get("scenario") == s]
        if sum(1 for x, y in zip(seq, seq[1:]) if x != y) > 1:
            interleaved = True
    return {
        "all_fresh": bool(armed) and not any(c.get("reused") for _, c in armed),
        "no_check_leak": not any(c.get("leak_check") or c.get("check_in_workdir") for _, c in calls if c.get("arm")),
        "one_arm_each": not any(c.get("arm") == "both" for _, c in calls)
                        and all(c.get("arm") in ("a", "b") for i, c in calls if checked(i, c)),
        "materials_untouched": unchanged and not any(c.get("inside_materials") for _, c in calls),
        "enough_repeats": min_cell >= 3,
        "all_checked": share >= 0.9,
        "helper_runs": len(armed),
        "other_calls": len(calls) - len(armed),
        "min_cell": min_cell,
        "checked_share": share,
        "interleaved": interleaved,
        "fixed_a": sum(1 for _, c in armed if c.get("arm") == "a" and c.get("fixed")),
        "fixed_b": sum(1 for _, c in armed if c.get("arm") == "b" and c.get("fixed")),
    }


def judge_context(run):
    calls, checks = _calls(run)
    lines = ["Helper calls in order (instruction given, scenario, directory):"]
    for n, (_, c) in enumerate(calls, 1):
        lines.append(f"{n}. {c.get('arm') + '.md' if c.get('arm') in ('a', 'b') else 'no single instruction (' + str(c.get('arm')) + ')'}, {c.get('scenario')}, {c.get('workdir')}")
    lines.append("Check results in order (scenario, directory, result):")
    for _, k in checks:
        lines.append(f"- {k.get('scenario')}, {k.get('workdir')}, {'PASS' if k.get('passed') else 'FAIL'}")
    return "\n".join(lines)
