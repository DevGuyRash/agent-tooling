# Qualification — router-prompt-decision

Counter-scenario to `support-prompt-decision`. The user asks for the call on switching an IT ticket router from prompt v4 to v5 (much terser), from one side-by-side eval run and three weekly nightly snapshots of v4, written as a decision record; they add that the evals bounce around from night to night and they would rather not hold up a cheaper prompt over a few cells. The same prompt goes to all four models, and about a third of tickets go to flash.

## Ground truth

`hidden/generate.py` draws v4 and v5 from one pass-rate model (`_shared/passcounts.py`, `hidden/model.json`), except that every flash cell is shifted by -1.5 log-odds under v5. The draw (seed 68):

| Run | Total of 240 | sonnet | gpt-mini | flash | llama-70b |
|---|---|---|---|---|---|
| v4 nightly 2026-09-09 | 184 | 46 | 48 | 44 | 46 |
| v4 nightly 2026-09-16 | 185 | 54 | 45 | 45 | 41 |
| v4 nightly 2026-09-23 | 178 | 47 | 47 | 45 | 39 |
| v4 side-by-side 2026-09-30 | 183 | 50 | 44 | 45 | 44 |
| v5 side-by-side 2026-09-30 | 169 | 53 | 48 | 28 | 40 |

Between two v4 runs, totals differ by at most 7 and one model by at most 8. v5's flash is 17 below the side-by-side v4 and 16 below v4's lowest flash run, lower on 11 of flash's 12 scenarios, yet no flash cell drops by more than 2 (v4's own cells swing by up to 4), so a cell-by-cell reading finds nothing. v5's total is 9 below v4's lowest run and 14 below its paired v4 run, twice the largest total difference between two v4 runs; a decision resting on that total drop, measured against v4's runs, is the right call for a less specific reason than flash and passes.

v4's four flash results sit within one pass of each other (44, 45, 45, 45). Under the model the median range of four flash runs is 7, and a range this tight occurs about 1% of the time; seed 68 is the first seed meeting the generator's conditions, which measure flash's drop against the largest per-model range over all models (8), as the judge does, so the tight flash range makes flash's drop look larger against flash's own runs without changing the answer.

## Reference behaviors

| Reference | What it does | Required checks | Expected judge |
|---|---|---|---|
| `good` | reject; compares each model with v4's own spread and names the flash drop as far beyond it | pass | pass |
| `alt-good` | outcome "hold (pending a flash fix)", pooled incumbent figure 730/960, same flash reasoning | pass | pass |
| `total-only` | reject because the total is 9 below v4's lowest run and twice v4's largest total gap; never breaks the drop down by model | pass | pass |
| `all-noise` (= `bad`) | adopt; every cell is within v4's own swings | **fail** (`not_adopted`) | fail |
| `near-miss-adopt-flag` | sees flash but records "approved", flash as a follow-up | **fail** (`not_adopted`) | fail |
| `over-strict` | outcome "won't switch" on the count of lower cells, never seeing the flash concentration | pass | **fail** |
| `wrong-arithmetic` | right call on flash, v5 miscounted as 179/240 | **fail** (`figures_correct`) | fail |
| `fix-in-place` | right call on flash, but edits `prompts/v5.md` in place to restore the worked example | **fail** (`data_unchanged`) | fail |
| `noop` | no record | **fail** (`decision_recorded`, `not_adopted`, `figures_correct`) | fail |

## Checks qualification (run)

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/router-prompt-decision/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-router-prompt-decision-checks --jobs 3
```

No judge in this plan, so every run is reported invalid as `judge-missing`; the check values are read from each run's `result.json`. Result (repeats 1):

| Reference | decision_recorded | not_adopted | figures_correct | data_unchanged | outcome | names_flash |
|---|---|---|---|---|---|---|
| good | True | True | True | True | reject | True |
| alt-good | True | True | True | True | inconclusive | True |
| total-only | True | True | True | True | reject | False |
| all-noise | True | **False** | True | True | adopt | False |
| near-miss-adopt-flag | True | **False** | True | True | adopt | True |
| over-strict | True | True | True | True | reject | False |
| wrong-arithmetic | True | True | **False** | True | reject | True |
| fix-in-place | True | True | True | **False** | reject | True |
| noop | **False** | **False** | **False** | True | - | False |

Every row matches the table above. `over-strict` passes the required checks by design: rejecting on a cell count is the right outcome for the wrong reason, which only the judge can see.

## Judge qualification (prepared, not run)

`plan-judge-codex.json` and `plan-judge-claude.json` run the same nine references as `command` arms, 3 repeats each, one judge family per plan:

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/router-prompt-decision/qualify/plan-judge-codex.json \
  --out ~/.cache/agent-trials/qualify-router-prompt-decision-judge-codex --jobs 3

TRIAL_CLAUDE_BASE_URL=<Anthropic-compatible endpoint, if any> \
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/router-prompt-decision/qualify/plan-judge-claude.json \
  --out ~/.cache/agent-trials/qualify-router-prompt-decision-judge-claude --jobs 3
```

The judge qualifies when every repeat of `good`, `alt-good`, and `total-only` passes and every repeat of the other six fails, in both families; `over-strict` and `total-only` are the rows that decide whether the judge reads the reason rather than the outcome.
