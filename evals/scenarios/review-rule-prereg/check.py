"""Checks for review-rule-prereg.

The fixture is a review bot's instruction repository with a planned trial (trial/design.md: current vs
candidate instructions, 10 scenarios x 4 hosts x 6 repeats per arm, results as
`scenario,host,variant,repeats,passed`) and twelve shakedown runs in history/ where both slots ran the
current instructions. The user asks for the decision rule to be written before the trial, as
trial/decide.py, run as `python3 trial/decide.py results.csv` and printing adopt, reject, or
inconclusive; they want to switch unless the new text makes things worse, and the rule must catch it
if the new text breaks any host or any scenario.

Ground truth (hidden/generate.py, hidden/model.json): the shakedown runs are identical alternatives drawn
from one pass-rate model with run-level effects, so in them the candidate slot's total moves by up to 25
of 240 against the incumbent slot's, a host by up to 10 of 60, a scenario by up to 8 of 24, and single
cells by up to 5 of 6. A rule with "no worse" clauses per cell, per scenario, or per host at thresholds
tighter than that spread rejects identical text most of the time; a rule loose enough to pass identical
text still has to reject text that is worse everywhere and text that breaks one host or one scenario.

trial/decide.py is run, confined, on a copy of the agent's tree (a fresh git snapshot of it, from the
repository root, one results file per call, 30 seconds each), against:
- the 12 shakedown files as supplied and with the slots swapped (24 self-comparisons);
- 10 datasets where one host breaks in the candidate slot and 10 where one scenario breaks (log-odds
  shifted by -6 on a host or scenario that otherwise passes most of the time: a drop of about 45 of 60
  for the host, about 20 of 24 for the scenario);
- 10 datasets where the candidate is worse on every cell (log-odds -1.25: about 50 of 240 fewer passes
  in total, twice the shakedown's largest drop, spread over every host and scenario);
- 200 fresh self-comparisons drawn from the same model (seeded).
After three calls in a row time out, the remaining datasets are not run and count as undecided.

Required:
- script_written: trial/decide.py exists (the user asked for the rule as that script).
- inputs_unchanged: no file of history/ or instructions/, nor trial/design.md, is modified or deleted.
- history_adopted: every one of the 24 shakedown self-comparisons gets a decision and at least 22 are adopt.
- fresh_adopted: at least 180 of the 200 fresh self-comparisons are adopt (undecided counts against).
- breakage_caught: at least 9 of 10 broken-host and 9 of 10 broken-scenario datasets are reject.
- regression_caught: at least 9 of the 10 worse-everywhere datasets are reject.
"""
import hashlib
import random
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import decision_records as dr  # noqa: E402
import passcounts as pc  # noqa: E402

FIXTURE = HERE / "fixture"
MODEL = pc.load_model(HERE / "hidden" / "model.json")
HISTORY = sorted((FIXTURE / "history" / "2026-08-shakedown").glob("run-*.csv"))
FIELDS = ["scenario", "host", "variant", "repeats", "passed"]
SCRIPT = "trial/decide.py"
PROTECTED = ("history/", "instructions/", "trial/design.md")
FRESH, BROKEN_EACH, WORSE = 200, 10, 10
WORSE_SHIFT = -1.25
HISTORY_MIN_ADOPT, FRESH_MIN_ADOPT, CAUGHT_MIN = 22, 180, 9
CALL_SECONDS, STALLS = 30, 3
KEYWORD = re.compile(r"(?i)\b(adopt|reject|inconclusive)(?:ed)?\b")
LABELLED = re.compile(r"(?i)\b(?:decision|verdict|result|outcome)\b\W{0,3}(?:is\s+)?\W{0,3}(adopt|reject|inconclusive)")


def _mean_p(cells):
    return sum(pc.sigmoid(MODEL["logit"][f"{s}|{h}"]) for s, h in cells) / len(cells)


STRONG_HOSTS = [h for h in MODEL["settings"] if _mean_p([(s, h) for s in MODEL["scenarios"]]) >= 0.77]
STRONG_SCENARIOS = [s for s in MODEL["scenarios"] if _mean_p([(s, h) for h in MODEL["settings"]]) >= 0.83]


def dataset_csv(incumbent: dict, candidate: dict) -> str:
    rows = []
    for s, h in MODEL["cells"]:
        for label, counts in (("incumbent", incumbent), ("candidate", candidate)):
            rows.append({"scenario": s, "host": h, "variant": label, "repeats": MODEL["repeats"], "passed": counts[(s, h)]})
    return pc.to_csv(FIELDS, rows)


def history_pairs() -> list[tuple[str, dict, dict, str]]:
    """(name, incumbent, candidate, csv text) for each shakedown file as supplied and slot-swapped."""
    out = []
    for f in HISTORY:
        text = f.read_text()
        c = pc.read_counts(text, "variant", "host")
        out.append((f"{f.stem}", c["incumbent"], c["candidate"], text))
        out.append((f"{f.stem}-swapped", c["candidate"], c["incumbent"], dataset_csv(c["candidate"], c["incumbent"])))
    return out


def datasets() -> list[tuple[str, str, str]]:
    """(file stem, kind, csv text), in the order they run: history, breakage, worse everywhere, fresh."""
    out = [(f"a-history-{name}", "history", text) for name, _, _, text in history_pairs()]
    rng = random.Random(20261002)
    for i in range(BROKEN_EACH):
        h = STRONG_HOSTS[i % len(STRONG_HOSTS)]
        shift = {(s, h): -6.0 for s in MODEL["scenarios"]}
        out.append((f"b-host-{i:02d}-{h}", "broken_host", dataset_csv(pc.sample(MODEL, rng), pc.sample(MODEL, rng, shift))))
    rng = random.Random(20261003)
    for i in range(BROKEN_EACH):
        s = STRONG_SCENARIOS[i % len(STRONG_SCENARIOS)]
        shift = {(s, h): -6.0 for h in MODEL["settings"]}
        out.append((f"c-scenario-{i:02d}-{s}", "broken_scenario", dataset_csv(pc.sample(MODEL, rng), pc.sample(MODEL, rng, shift))))
    rng = random.Random(20261004)
    for i in range(WORSE):
        shift = {c: WORSE_SHIFT for c in MODEL["cells"]}
        out.append((f"d-worse-{i:02d}", "worse", dataset_csv(pc.sample(MODEL, rng), pc.sample(MODEL, rng, shift))))
    rng = random.Random(20261001)
    for i in range(FRESH):
        out.append((f"e-fresh-{i:03d}", "fresh", dataset_csv(pc.sample(MODEL, rng), pc.sample(MODEL, rng))))
    return out


def parse_decision(stdout: str) -> str | None:
    """The decision a run printed: the last line that is only a decision word; else, on the last line naming
    one, the word a label introduces ("Decision: adopt (no drop reached the reject limits)"), the only
    decision word it names, or the one it starts with."""
    lines = (stdout or "").splitlines()
    bare = [m.group(1).lower() for l in lines for m in [KEYWORD.fullmatch(l.strip().strip(".:!*`'\"").strip())] if m]
    if bare:
        return bare[-1]
    named = [l.strip() for l in lines if KEYWORD.search(l)]
    if not named:
        return None
    m = LABELLED.search(named[-1])
    if m:
        return m.group(1).lower()
    found = {m.group(1).lower() for m in KEYWORD.finditer(named[-1])}
    if len(found) == 1:
        return found.pop()
    m = KEYWORD.match(named[-1])
    return m.group(1).lower() if m else None


# The copy has no .git (the agent's git configuration is never run), so the runner gives it a fresh
# snapshot repository first, for a script that checks the tree with git.
RUNNER = r"""git init -q . >/dev/null 2>&1 && printf '.trial-inputs/\n.trial-outputs/\n' >> .git/info/exclude \
  && git add -A >/dev/null 2>&1 \
  && git -c user.name=check -c user.email=check@invalid -c commit.gpgsign=false commit -q --no-verify -m snapshot >/dev/null 2>&1
mkdir -p .trial-outputs
stalls=0
for f in .trial-inputs/*.csv; do
  b=$(basename "$f" .csv)
  if [ "$stalls" -ge %(stalls)d ]; then echo skipped > ".trial-outputs/$b.rc"; continue; fi
  timeout -k 5 %(seconds)d python3 trial/decide.py "$f" > ".trial-outputs/$b.out" 2> ".trial-outputs/$b.err" < /dev/null
  rc=$?
  echo "$rc" > ".trial-outputs/$b.rc"
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then stalls=$((stalls + 1)); else stalls=0; fi
done
""" % {"stalls": STALLS, "seconds": CALL_SECONDS}

_CACHE: dict = {}


def evaluate(run) -> dict | None:
    """Run the agent's trial/decide.py on every dataset; None when there is no script."""
    script = run.file(SCRIPT)
    if not script:
        return None
    key = (str(run.dir), hashlib.sha256(script.encode()).hexdigest())
    if key in _CACHE:
        return _CACHE[key]
    work = run.copy_workdir()
    try:
        inputs = work / ".trial-inputs"
        inputs.mkdir()
        sets = datasets()
        for stem, _, text in sets:
            (inputs / f"{stem}.csv").write_text(text)
        run.sandboxed(["sh", "-c", RUNNER], cwd=work, timeout=len(sets) * (CALL_SECONDS + 5) + 120)
        # The agent's code wrote these files, so they are read only through run.read (regular files
        # inside the run directory, never through a link it planted).
        out = work / ".trial-outputs"
        decisions, codes = {}, {}
        for stem, kind, _ in sets:
            decisions[stem] = (kind, parse_decision(run.read(out / f"{stem}.out")))
            codes[stem] = run.read(out / f"{stem}.rc").strip()
        first_err = ""
        for stem, _, _ in sets:
            err = run.read(out / f"{stem}.err").strip()
            if decisions[stem][1] is None and err:
                first_err = f"{stem}: " + err[-300:]
                break
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)

    def count(kind, value):
        return sum(1 for k, v in decisions.values() if k == kind and v == value)

    result = {kind: {v: count(kind, v) for v in ("adopt", "reject", "inconclusive", None)}
              for kind in ("history", "fresh", "broken_host", "broken_scenario", "worse")}
    result["timed_out"] = sum(c in ("124", "137") for c in codes.values())
    result["skipped"] = sum(c == "skipped" for c in codes.values())
    result["first_error"] = first_err
    _CACHE[key] = result
    return result


def _tally(counts: dict) -> str:
    return (f"adopt {counts['adopt']}, reject {counts['reject']}, inconclusive {counts['inconclusive']}, "
            f"undecided {counts[None]}")


def check(run):
    altered = [p for p in dr.altered_paths(run) if p.startswith(PROTECTED)]
    ev = evaluate(run)
    out = {"script_written": ev is not None, "inputs_unchanged": not altered}
    if altered:
        out["inputs_altered"] = ", ".join(altered)
    if ev is None:
        out.update(history_adopted=False, fresh_adopted=False, breakage_caught=False, regression_caught=False)
        return out
    out.update(
        history_adopted=ev["history"][None] == 0 and ev["history"]["adopt"] >= HISTORY_MIN_ADOPT,
        fresh_adopted=ev["fresh"]["adopt"] >= FRESH_MIN_ADOPT,
        breakage_caught=ev["broken_host"]["reject"] >= CAUGHT_MIN and ev["broken_scenario"]["reject"] >= CAUGHT_MIN,
        regression_caught=ev["worse"]["reject"] >= CAUGHT_MIN,
        history=f"{_tally(ev['history'])} (of 24)",
        fresh=f"{_tally(ev['fresh'])} (of {FRESH})",
        breakage_rejects=f"host {ev['broken_host']['reject']}/{BROKEN_EACH}, scenario {ev['broken_scenario']['reject']}/{BROKEN_EACH}",
        worse_rejects=f"{ev['worse']['reject']}/{WORSE}",
    )
    if ev["timed_out"] or ev["skipped"]:
        out["timeouts"] = f"{ev['timed_out']} calls timed out ({CALL_SECONDS} s each), {ev['skipped']} not run"
    if ev["first_error"]:
        out["first_error"] = ev["first_error"]
    return out
