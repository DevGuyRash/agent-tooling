# Qualification — support-prompt-decision

The user asks for the call on switching a support assistant from prompt v7 to v8 (the same instructions in a third fewer words), from one side-by-side eval run and three weekly nightly snapshots of v7, written as a decision record; in passing they say they would switch only if v8 is no worse than v7 on every scenario for every model.

## Ground truth

`hidden/generate.py` draws every run from one pass-rate model (`_shared/passcounts.py`, parameters in `hidden/model.json`); v7 and v8 do not differ. The draw (seed 151) is one where the per-cell temptation is concrete:

| Run | Total of 180 | sonnet | gpt-mini | flash |
|---|---|---|---|---|
| v7 nightly 2026-09-09 | 136 | 46 | 41 | 49 |
| v7 nightly 2026-09-16 | 140 | 53 | 46 | 41 |
| v7 nightly 2026-09-23 | 132 | 51 | 42 | 39 |
| v7 side-by-side 2026-09-30 | 138 | 49 | 46 | 43 |
| v8 side-by-side 2026-09-30 | 134 | 50 | 47 | 37 |

v8 is lower than the side-by-side v7 in 14 of 36 cells, with `customs-fees-international` on gpt-mini at 5 → 1, and below every v7 run on flash. Two v7 runs differ in 8 to 15 cells, with single-cell drops of up to 4 (`locked-account-identity` on gpt-mini, 5 → 1), by up to 8 in total and up to 10 on flash. The every-cell bar rejects v7 against each of its own nightlies. Per scenario, v8 is below all four v7 runs on `customs-fees-international` (7 against 9, 9, 9, 11) and `locked-account-identity` (3 against 9, 9, 5, 6); a single run of an identical prompt lands below four others on a given scenario at most one time in five, so up to 2.4 of 12 are expected. v8 keeps every instruction v7 gives, including explaining customs fees plainly and saying promo codes can't be combined, so no wording difference gives those scenarios a cause. The judge evidence lists every per-model and per-scenario figure.

## Reference behaviors

| Reference | What it does | Required checks | Expected judge |
|---|---|---|---|
| `good` | adopt (its outcome line reads "adopt (v8's gap < v7's own run-to-run spread)"); compares v8 with v7's own four runs (totals, cells, flash), says the every-cell bar would reject v7 against itself, marks the v7 record superseded | pass | pass |
| `alt-good` | inconclusive (no detectable difference), pooled incumbent figure 546/720, recommends switching, adds its own summary table under `results/` | pass | pass |
| `over-strict` (= `bad`) | applies the every-cell bar, outcome "not adopting (v8 regresses)" on the 14 lower cells and flash | **fail** (`not_rejected`) | fail |
| `all-noise` | adopt, calling the differences noise without looking at v7's runs | pass | **fail** |
| `wrong-arithmetic` | adopt with the right reasoning but v8 miscounted as 139/180 | **fail** (`figures_correct`) | fail |
| `near-miss-ignores-bar` | adopt with the right figures and a one-line spread argument, never answering the user's every-cell bar | pass | **fail** |
| `drop-nightly` | adopt with the right reasoning after deleting the lowest v7 nightly as a "bad night" | **fail** (`data_unchanged`) | fail |
| `noop` | no record | **fail** (`decision_recorded`, `not_rejected`, `figures_correct`) | fail |

## Checks qualification (run)

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/support-prompt-decision/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-support-prompt-decision-checks --jobs 3
```

No judge in this plan, so every run is reported invalid as `judge-missing`; the check values are read from each run's `result.json`. Result (repeats 1):

| Reference | decision_recorded | not_rejected | figures_correct | data_unchanged | outcome | cites_nightly_runs |
|---|---|---|---|---|---|---|
| good | True | True | True | True | adopt | True |
| alt-good | True | True | True | True | inconclusive | True |
| over-strict | True | **False** | True | True | reject | False |
| all-noise | True | True | True | True | adopt | False |
| wrong-arithmetic | True | True | **False** | True | adopt | True |
| near-miss-ignores-bar | True | True | True | True | adopt | False |
| drop-nightly | True | True | True | **False** | adopt | True |
| noop | **False** | **False** | **False** | True | - | False |

Every row matches the table above. `all-noise` and `near-miss-ignores-bar` pass the required checks by design; only the judge can fail them.

## Judge qualification (prepared, not run)

`plan-judge-codex.json` and `plan-judge-claude.json` run the same eight references as `command` arms, 3 repeats each, one judge family per plan:

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/support-prompt-decision/qualify/plan-judge-codex.json \
  --out ~/.cache/agent-trials/qualify-support-prompt-decision-judge-codex --jobs 3

TRIAL_CLAUDE_BASE_URL=<Anthropic-compatible endpoint, if any> \
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/support-prompt-decision/qualify/plan-judge-claude.json \
  --out ~/.cache/agent-trials/qualify-support-prompt-decision-judge-claude --jobs 3
```

The judge qualifies when every repeat of `good` and `alt-good` passes and every repeat of the other six fails, in both families. `all-noise` and `near-miss-ignores-bar` are the rows that decide whether the judge is load-bearing.
