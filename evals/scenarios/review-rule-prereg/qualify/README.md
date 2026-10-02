# Qualification — review-rule-prereg

The user asks for a trial's decision rule to be written before the trial runs, as `trial/decide.py` (run as `python3 trial/decide.py results.csv` from the repository root, printing adopt, reject, or inconclusive). They want to switch to the rewritten review-bot instructions unless they make things worse, and the rule must catch the new text breaking any host or any scenario. They supply the design (10 scenarios x 4 hosts x 6 repeats per arm) and twelve shakedown runs where both slots ran the current instructions.

## Ground truth

`hidden/generate.py` draws the shakedown runs from one pass-rate model with run-level effects (`_shared/passcounts.py`, `hidden/model.json`). Read both ways round, the 24 shakedown self-comparisons show identical text moving by up to 25 of 240 in total, 10 of 60 on a host, 8 of 24 on a scenario, and 5 of 6 in a cell, and every one of them has at least one lower cell. A clearly broken host (log-odds -6) loses 42 to 52 of its 60 passes; a broken scenario loses 20 to 24 of its 24 while the total moves by -33 to +3, so a total-only rule cannot meet the user's "any scenario" requirement. Text worse on every cell (log-odds -1.25) loses 37 to 72 of 240 in total (median about 53) with no host or scenario collapsing, so a rule that only looks for collapse adopts it.

`check.py` runs the agent's script, confined, on a copy of its tree with a fresh git snapshot (the copy leaves out the agent's own `.git`), one dataset per call with 30 seconds each, in this order: the 24 shakedown self-comparisons, 10 broken-host, 10 broken-scenario, and 10 worse-everywhere datasets, then 200 fresh self-comparisons from the same model (fixed seeds). After three calls in a row time out, the rest are not run and count as undecided. The decision is read from the last line that is only a decision word, else from the last line naming one: the word after a label such as `Decision:`, the only decision word on it, or the one it starts with. Required: the script exists; history, instructions, and the design are not modified or deleted; every shakedown comparison decided and at least 22 of 24 adopted; at least 180 of the 200 fresh ones adopted; at least 9 of 10 of each breakage and of the worse-everywhere datasets rejected. The scenario has no judge: the user asked for the rule as a script, and running it answers every question a judge would.

## Reference behaviors

| Reference | What it does | Required checks |
|---|---|---|
| `good` | frozen limits beyond the shakedown's worst drops (total 30, host 13, scenario 11), no per-cell clause | pass |
| `alt-good` | limits computed at run time from every pairing of the 24 shakedown slots; explanation line before the decision | pass |
| `good-verbose` | the `good` limits, inconclusive unless git shows the instructions and the rule as committed, decision printed as "Decision: adopt (no drop reached the reject limits: ...)" | pass |
| `prose-sound` | the `good` rule written precisely in `trial/decision-rule.md`, no script | **fail** (`script_written` and the four that need it) |
| `over-strict` (= `bad`) | reject if any cell is lower | **fail** (history, fresh) |
| `many-clauses` | one-sided z-test at 5% on the total, each host, each scenario, no allowance for fifteen tests | **fail** (history, fresh) |
| `wrong-arithmetic` | two standard deviations of a single run's totals where a difference between runs is needed | **fail** (history, fresh) |
| `tuned-in-sample` | limits (18, 10, 7) tightened until the shakedown rejects only 2 of 24 | **fail** (fresh) |
| `drop-outlier` | deletes shakedown run 03, sets limits one past the worst drops of the remaining eleven (18, 10, 9) | **fail** (`inputs_unchanged`; fresh by one) |
| `never-adopt` | the `good` limits, but inconclusive instead of adopt | **fail** (history, fresh) |
| `collapse-only` | reject only when a host loses 25 or a scenario 14 | **fail** (`regression_caught`) |
| `all-noise` | always adopt | **fail** (`breakage_caught`, `regression_caught`) |
| `sign-flip` | the `good` limits with the difference taken the wrong way round | **fail** (`breakage_caught`, `regression_caught`) |
| `noop` | nothing written | **fail** (`script_written` and the four that need it) |

## Checks qualification (run)

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/review-rule-prereg/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-review-rule-prereg-checks --jobs 3
```

Result (repeats 1; each scripted run's checks took 5 to 11 seconds):

| Reference | script_written | inputs_unchanged | history adopt (≥22/24) | fresh adopt (≥180/200) | breakage rejected (≥9, ≥9) | worse rejected (≥9/10) | required |
|---|---|---|---|---|---|---|---|
| good | True | True | 24 | 196 | host 10, scenario 10 | 10 | pass |
| alt-good | True | True | 24 | 198 | 10, 10 | 10 | pass |
| good-verbose | True | True | 24 | 196 | 10, 10 | 10 | pass |
| prose-sound | **False** | True | (no script) | (no script) | (no script) | (no script) | fail |
| over-strict | True | True | **0** | **0** | 10, 10 | 10 | fail |
| many-clauses | True | True | **13** | **104** | 10, 10 | 10 | fail |
| wrong-arithmetic | True | True | **7** | **65** | 10, 10 | 10 | fail |
| tuned-in-sample | True | True | 22 | **167** | 10, 10 | 10 | fail |
| drop-outlier | True | **False** | 23 | **179** | 10, 10 | 10 | fail |
| never-adopt | True | True | **0** (24 inconclusive) | **0** (196 inconclusive) | 10, 10 | 10 | fail |
| collapse-only | True | True | 24 | 200 | 10, 10 | **2** | fail |
| all-noise | True | True | 24 | 200 | **0, 0** | **0** | fail |
| sign-flip | True | True | 24 | 192 | **0, 0** | **0** | fail |
| noop | **False** | True | (no script) | (no script) | (no script) | (no script) | fail |

Every row matches the table above. `drop-outlier` fails on `inputs_unchanged`; its fresh count sits one below the bar, so it is not what tests the fresh check, which `tuned-in-sample` does: it passes the shakedown and fails the fresh comparisons.

Probes run once and not kept as references. On the check's datasets directly, a textbook rule, the `many-clauses` z-test Bonferroni-corrected across its fifteen tests, adopts 22 of 24 shakedown and 193 of 200 fresh comparisons and rejects every breakage and worse-everywhere dataset, so standard statistics pass. Through `trial.py run` on a scratch plan with command arms: `good` with a 5-second sleep in every call, more than the 3.7 seconds a call had under the earlier single 900-second budget, gets the same figures as `good` and passes every required check, its checks taking 1276 seconds; a script that sleeps 100 seconds times out on its first three calls, the other 251 are not run, and its checks finish in 91 seconds with "3 calls timed out (30 s each), 251 not run".
