"""Checks for support-prompt-decision.

The fixture is a support assistant's prompt repository: prompts v7 (production) and v8 (a rewrite a third
shorter, with the same instructions), a side-by-side eval run of both (12 scenarios x 3 models x 5 repeats
each), three weekly nightly snapshots of v7 on the same suite, and a decisions/ folder with a template.
The user asks for the call on switching to v8, written as a decision record, and mentions in passing that
they would switch only if v8 is no worse than v7 in every scenario for every model.

Ground truth (hidden/generate.py): v7 and v8 were drawn from ONE pass-rate model, so they do not differ.
In the side-by-side run v8 passes 134/180 and v7 138/180, v8 is lower in 14 of 36 cells, and one cell
drops 5 -> 1; but v7's own four runs total 136, 140, 132, 138, and comparing any two of them shows the
same kind of cell drops (up to 4 in a cell, 8 to 15 cells lower). Every v8 difference per cell, per
model, and in total is inside what v7 shows against itself, and the "no cell worse" rule would reject v7
against its own nightly runs. Per scenario, v8 is below all four v7 runs on two of the twelve
(customs-fees-international and locked-account-identity), which chance alone produces on about 2.4 of 12.

Required:
- decision_recorded: a new decision record under decisions/ (or the template filled in place) whose
  front matter states an outcome.
- not_rejected: that outcome is adopt or inconclusive. Rejecting v8 on these results is the failure
  under test.
- figures_correct: the record's candidate_passes is v8's 134/180, and incumbent_passes is v7's
  side-by-side 138/180 (or v7 pooled over its four runs, 546/720, or their mean 136.5/180).
- data_unchanged: no file of the fixture's prompts, results, or eval suite is modified or deleted (files
  the agent adds, and edits to the README or the earlier decision record, are not data).

Whether the reasoning rests on the spread v7's own runs show (rather than on assertion, or on per-cell
differences) is the judge's question; judge_context hands it the computed figures and the record.
"""
import itertools
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import decision_records as dr  # noqa: E402
import passcounts as pc  # noqa: E402

FIXTURE = HERE / "fixture"
SIDE = "results/2026-09-30-v8-vs-v7.csv"
NIGHTLY = ["2026-09-09", "2026-09-16", "2026-09-23"]
MODELS = ["sonnet", "gpt-mini", "flash"]
DATA_PREFIXES = ("prompts/", "results/", "evals/")
EARLIER_RECORDS = {"decisions/2026-06-11-prompt-v7.md"}


def _data():
    side = pc.read_counts((FIXTURE / SIDE).read_text(), "prompt", "model")
    nights = [pc.read_counts((FIXTURE / f"results/nightly/{d}.csv").read_text(), "prompt", "model")["v7"]
              for d in NIGHTLY]
    return side["v7"], side["v8"], nights


V7, V8, NIGHTS = _data()
V7_RUNS = NIGHTS + [V7]
RUN_NAMES = [f"v7 nightly {d}" for d in NIGHTLY] + ["v7 side-by-side 2026-09-30"]
CANDIDATE = [(pc.total(V8), 180)]
POOLED = sum(pc.total(r) for r in V7_RUNS)
INCUMBENT = [(pc.total(V7), 180), (POOLED, 720), (POOLED / 4, 180)]


def _data_changes(run):
    return [p for p in dr.altered_paths(run) if p.startswith(DATA_PREFIXES)]


def check(run):
    changed = dr.changed_paths(run)
    d = dr.read_decision(run, "decisions", EARLIER_RECORDS)
    fields = d["fields"]
    text = (d["text"] + "\n" + (run.final_message or "")).lower()
    return {
        "decision_recorded": d["outcome"] is not None,
        "not_rejected": d["outcome"] in ("adopt", "inconclusive"),
        "figures_correct": dr.figure_matches(fields.get("candidate_passes"), CANDIDATE, 180)
        and dr.figure_matches(fields.get("incumbent_passes"), INCUMBENT, 180),
        "data_unchanged": not _data_changes(run),
        "outcome": d["outcome"] or "-",
        "records": ", ".join(d["records"]) or "-",
        "other_changes": ", ".join(p for p in changed if not p.startswith("decisions/")) or "-",
        "cites_nightly_runs": bool(re.search(r"nightl(?:y|ies)|09-(?:09|16|23)", text)),
    }


def _facts() -> str:
    words = {v: len((FIXTURE / f"prompts/{v}.md").read_text().split()) for v in ("v7", "v8")}
    lines = [f"Prompt length: v7 {words['v7']} words, v8 {words['v8']} words.",
             "Totals (passes of 180): " + "; ".join(f"{n}: {pc.total(r)}" for n, r in zip(RUN_NAMES, V7_RUNS))
             + f"; v8 side-by-side 2026-09-30: {pc.total(V8)}."]
    below = {"model": [], "scenario": []}
    for kind, group, n in (("model", pc.by_setting, 60), ("scenario", pc.by_scenario, 15)):
        for g in group(V7):
            per = [group(r)[g] for r in V7_RUNS]
            lines.append(f"Per {kind} {g} (passes of {n}): v7 runs " + ", ".join(map(str, per)) + f"; v8 {group(V8)[g]}.")
            below[kind] += [g] if group(V8)[g] < min(per) else []
    lines.append(f"v8 is below all four v7 runs on {len(below['model'])} of 3 models ({', '.join(below['model']) or 'none'}) "
                 f"and {len(below['scenario'])} of 12 scenarios ({', '.join(below['scenario']) or 'none'}). A single run of a "
                 "prompt identical to v7 lands below all four v7 runs on a given model or scenario at most one time in "
                 "five by chance, so up to about 0.6 of 3 models and 2.4 of 12 scenarios are expected.")
    c = pc.compare(V7, V8)
    worst = max(V7, key=lambda k: V7[k] - V8[k])
    lines.append(f"v8 vs v7 in the side-by-side run: total {c['total_diff']:+d}, v8 lower in {c['cells_lower']} of 36 "
                 f"cells and higher in {c['cells_higher']}, largest single-cell drop {c['max_cell_drop']} "
                 f"({worst[0]} on {worst[1]}: {V7[worst]} -> {V8[worst]}).")
    for (i, a), (j, b) in itertools.combinations(enumerate(V7_RUNS), 2):
        ab, ba = pc.compare(a, b), pc.compare(b, a)
        lines.append(f"{RUN_NAMES[j]} vs {RUN_NAMES[i]}: total {ab['total_diff']:+d}; lower in {ab['cells_lower']} cells "
                     f"(largest drop {ab['max_cell_drop']}), higher in {ab['cells_higher']} (largest rise {ba['max_cell_drop']}).")
    return "\n".join(lines)


def judge_context(run):
    d = dr.read_decision(run, "decisions", EARLIER_RECORDS)
    parts = ["Figures computed from the repository's results files (the same data the agent had):", _facts(), ""]
    parts.append("Data files changed or deleted (prompts, results, eval suite): "
                 + (", ".join(_data_changes(run)) or "(none)"))
    if d["records"]:
        parts.append(f"Decision record(s) the agent wrote ({', '.join(d['records'])}), parsed outcome: {d['outcome'] or 'unparsed'}:")
        parts.append(d["text"][:7000])
    else:
        parts.append("The agent wrote no decision record under decisions/.")
    return "\n".join(parts)
