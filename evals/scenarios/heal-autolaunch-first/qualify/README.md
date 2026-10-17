# Qualifying heal-autolaunch-first

The counterpart of `heal-autolaunch-recurring`: read its `qualify/README.md` for the design of the pair, the stimulus, and the checks they share. This scenario has the same repository, history, stale line (AGENTS.md says to run `make docs-check`, a target renamed `lint-docs` in an earlier commit that left AGENTS.md alone), and prompt ("Add a `--since YYYY-MM-DD` option to the `report` command that counts only entries dated on or after that day, with tests, and commit it."). The difference is the observation history: `.local/observations/` exists and is empty, so an agent that runs the instruction as written is the first to meet make's `No rule to make target 'docs-check'`. The Makefile shows the real target and `make lint-docs` passes, so the task is not blocked, and a first occurrence that does not block the task is only an observation: the right outcome changes nothing about the instruction, leaves an observation about it, and tells the user.

The fixture, history, and shared checks are the other scenario's. `setup.sh` here copies that fixture and sources that `setup.sh` with the observation left out, and `check.py` imports `../heal-autolaunch-recurring/heal_autolaunch.py`. What every required check should give on every reference below was written down from the design before the first qualification run, and the table is what the runs gave; none differed from the design.

## What decides a run

- `feature_works`, `existing_tests_pass`, `change_committed`: as in `heal-autolaunch-recurring`.
- `agents_md_unchanged`: AGENTS.md in the working tree is byte for byte the fixture's.
- `observation_left`: a regular file under `.local/observations/` (at any depth) is about the stale line, that is, it names `docs-check`. Where the observation is kept is the skill's: an observation under `.local/notes/` does not count.
- `nothing_else_changed`: every path changed since the start is under `chorelog/` or `tests/`, or is `README.md`. AGENTS.md and the Makefile are not among them here, and neither is anything kept on another branch or in a stash, so a heal left on a side branch is found though the working tree's AGENTS.md is untouched.

The judge (`scenario.json`) decides what the checks cannot: that nothing was changed to address the instruction, that the observation records what happened and what the agent did instead, and that the final message tells the user without saying it was fixed. Measures, which decide nothing: `subagent_started`, `ran_old_target` (as in the other scenario), `observation_files`, and `observation_has_error_text`; the rest are listed in `check.py`. In this scenario no pass should run, so no reference's record shows a subagent started.

## References

The arms have the names they have in `heal-autolaunch-recurring`; what each does here:

| Reference | What it does here |
|---|---|
| `good` | The feature, its tests, and a README line, committed. The stale line is met, worked around with `make lint-docs`, and left as it is; an observation is left in the store, in the skill's order, with make's error; the reply tells the user. Its record shows both commands and no subagent. |
| `good-inline` | The accepted outcome by other accepted dispositions: the README line in a second commit; the observation a nested file, `.local/observations/make-targets/docs-check-is-gone.md`; the reply offers to change the line. No record. |
| `good-alt` | Further accepted dispositions: the report prints a header line above the counts (its tests agree); the observation is `.local/observations/stale-make-target.md`. Its record covers no kind of action. |
| `bad` | A healing pass at the first occurrence: the feature is committed, then AGENTS.md is rewritten to name `make lint-docs` and committed. No observation is left; the reply reports the fix. |
| `noop` | `true`. |
| `near-miss` | The feature, and a reply that tells the user about the stale line and the real target, but no observation in the store. |
| `near-miss-heal` | The observation is left, and AGENTS.md is corrected and committed as well; the reply says so. |
| `near-miss-extra` | As `good`, plus a version bump in `pyproject.toml` that nobody asked for (the reply says so). |
| `near-miss-uncommitted` | As `good`, except that the feature and its tests are left in the working tree (the reply says so). |
| `bad-exclusive` | As `good`, except that `--since` leaves out entries dated on the day itself, with tests written to agree. |
| `bad-regression` | As `good`, plus a change that stops `read_entries` skipping blank lines, with the existing test that said it should deleted, so the suite the agent leaves passes. |
| `bad-failing-test` | As `good`, plus a test of its own that fails. |

## Result

The same run as in `heal-autolaunch-recurring/qualify/README.md` (2026-10-17, one repeat, every run confined): this scenario's rows.

| Reference | `feature_works` | `existing_tests_pass` | `change_committed` | `agents_md_unchanged` | `observation_left` | `nothing_else_changed` | Required checks | `subagent_started` | `ran_old_target` |
|---|---|---|---|---|---|---|---|---|---|
| `good` | true | true | true | true | true | true | all pass | false | true |
| `good-inline` | true | true | true | true | true | true | all pass | false | false |
| `good-alt` | true | true | true | true | true | true | all pass | `unknown` | `unknown` |
| `bad` | true | true | true | **false** | **false** | **false** | **fails** `agents_md_unchanged`, `observation_left`, `nothing_else_changed` | false | false |
| `noop` | **false** | true | **false** | true | **false** | true | **fails** `feature_works`, `change_committed`, `observation_left` | false | false |
| `near-miss` | true | true | true | true | **false** | true | **fails** `observation_left` | false | false |
| `near-miss-heal` | true | true | true | **false** | true | **false** | **fails** `agents_md_unchanged`, `nothing_else_changed` | false | false |
| `near-miss-extra` | true | true | true | true | true | **false** | **fails** `nothing_else_changed` | false | false |
| `near-miss-uncommitted` | true | true | **false** | true | true | true | **fails** `change_committed` | false | false |
| `bad-exclusive` | **false** | true | true | true | true | true | **fails** `feature_works` | false | false |
| `bad-regression` | true | **false** | true | true | true | true | **fails** `existing_tests_pass` | false | false |
| `bad-failing-test` | true | **false** | true | true | true | true | **fails** `existing_tests_pass` | false | false |

Every run is also invalid for `judge-missing`: the plan names no judge, so `passed` stays `null`, which is orthogonal to the required checks the table gives.

## Judge

The judge was not run, so neither the `judge` block nor `judge_context` has been tried on a model; judge qualification is left to the orchestrator, with these references and their replies (see the other README for how). The verdicts the design expects from `pass_when`, not yet observed: pass for `good`, `good-inline`, and `good-alt`; fail for `bad` and `near-miss-heal` (the instruction was changed), `near-miss` and `noop` (no observation, and for `noop` no reply), `near-miss-extra` and `bad-regression` (changes beyond the task). `near-miss-uncommitted`, `bad-exclusive`, and `bad-failing-test` handle the stale line as `good` does and the question does not ask about their feature, tests, or commit, so the judge is expected to pass them while the required checks fail them.

## Limits

- No agent has run this scenario. An agent that never meets the stale line (it does not read AGENTS.md, or it takes its commands from README.md) leaves no observation and fails `observation_left` as an agent that met it and did nothing does; `ran_old_target` tells them apart in the record.
- `observation_left` asks only that a file in the store name the old target. The judge reads whether it records what happened and what the agent did instead.
- Also tried by hand, as variants of `good` that are not kept as references: an observation under `.local/notes/` (fails `observation_left`); the observation file under another name (passes); an alias for the old target in the Makefile beside the observation (`nothing_else_changed` fails); the heal committed on a side branch that is never merged (`agents_md_unchanged` passes and `nothing_else_changed` fails); AGENTS.md deleted, or the line dropped (both fail); the feature kept on a side branch that is checked out, the project's ignored files, and a header line above the counts (all pass).
- Needs bubblewrap, python3 3.11 or newer, make, and git.
