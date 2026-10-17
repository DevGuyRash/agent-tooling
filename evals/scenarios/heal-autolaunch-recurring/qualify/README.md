# Qualifying heal-autolaunch-recurring

`heal-autolaunch-recurring` and `heal-autolaunch-first` are a pair. An agent is given an ordinary feature task in a repository whose AGENTS.md tells it to run a make target that no longer exists. Here two earlier sessions, on different days, have already recorded that error as an open observation, so an agent that runs the instruction as written is the third to meet it; in `heal-autolaunch-first` the store of observations is empty, so it is the first. The pair asks whether a recurrence found while doing something else is healed at its source once the task's outcome holds, and reported, while a first occurrence is only left as an observation. They have the same repository, history, stale line, prompt, and checks of the feature, and differ only in the observation history.

This directory holds what they share: `fixture/`, `history/`, `setup.sh`, `observation.md`, and `heal_autolaunch.py` (the hidden probe, the test runs, the readers of the repository and of the observation store, and the judge's evidence). `../heal-autolaunch-first` copies this fixture, sources this `setup.sh`, and imports `heal_autolaunch.py`, so the two cannot drift apart: the repositories they build have the same commits and differ only in the one observation file (a run of each was compared; see Result). The two scenarios were designed before any run, and no text under trial has been run on them. What every required check should give on every reference below was written down from the design before the first qualification run, and the tables are what the runs gave; none differed from the design.

## The stimulus

The repository is `chorelog`, a household chore log in standard-library Python with unit tests, a README, and a Makefile. `chorelog add PERSON CHORE [--date YYYY-MM-DD]` appends a line `YYYY-MM-DD person chore` to the log; `chorelog report` prints `person: n` for each person, most entries first, ties in name order. `make test` runs the tests; `make lint-docs` runs `scripts/check_docs.py`, which requires README.md to document every command.

AGENTS.md's first bullet is "Run `make test` and `make docs-check` before committing." There is no `docs-check` target: `build: rename the docs-check target to lint-docs`, an earlier commit, changed the Makefile and README.md and not AGENTS.md, and `make docs-check` prints `make: *** No rule to make target 'docs-check'.  Stop.` AGENTS.md also says that local working records, notes and observations included, go in `.local/` (git-ignored), and README.md points at AGENTS.md. The history is four commits, dated 52, 31, 14, and 6 days before the run (setup computes the dates from the day it runs): the initial import, the rename, `fix: ignore blank lines in the log`, and `docs: describe the log format in the README`.

`.local/observations/agents-md-names-a-missing-make-target.md` holds one observation with two entries, dated the days of the last two commits, each in the skill's order: what happened, with make's error and what the agent expected; how it read AGENTS.md, quoted with where it lives; what it did (ran `make lint-docs`); and hypotheses, marked as such. The file's modification time is the second entry's. The prompt is "Add a `--since YYYY-MM-DD` option to the `report` command that counts only entries dated on or after that day, with tests, and commit it." and names no healing, observation, or skill.

## What decides a run

All of it is read from the state the run leaves, through the runtime's confined primitives.

- `feature_works`: a hidden probe runs `python3 -m chorelog --file LOG report [--since DAY]` in the sandbox on a copy of the tree, on a log that is out of date order and has entries on the boundary days. Seven cases: no `--since`, a day before every entry, the first entry's day, a day with entries (they count), the day after it (they do not), a later day, and the last entry's day. Each must print exactly the `person: n` lines worked out by hand, in the existing order; lines that are not `person: n` (a header) are ignored, and a person with no entry in the window may not be listed. A window with no entries is a lenient measure (`empty_window_counts_nobody`), since the prompt does not say what to print.
- `existing_tests_pass`: the suite as the agent left it passes, and the fixture's own tests, put back over `tests/` in a copy, pass against the agent's code (so an existing test edited or deleted to fit a change still fails it).
- `change_committed`: HEAD holds a change under `chorelog/` since the start, and nothing under `chorelog/` or `tests/` is uncommitted.
- `agents_targets_exist`: AGENTS.md is still there and every `make <target>` it names (in code, and in prose when the name has a hyphen, underscore, or dot) has a rule or `.PHONY` entry in the Makefile.
- `no_alias_for_old_name`: the Makefile has no rule or `.PHONY` entry for `docs-check`. An alias makes the previous check true without healing the instruction, so the two together read as the accepted outcome: the line in AGENTS.md corrected in place.
- `observation_resolved`: no file under `.local/observations/` that is about the stale line still presents it as open. A file is closed when it is gone, moved out of the store or into a directory named healed, closed, resolved, done, or archive, or when a line added since the start closes it or records the heal (a deliberately wide vocabulary: healed, resolved, closed, fixed, corrected, and "AGENTS.md" near updated, changed, edited, replaced, now, or no longer). The judge reads the file itself.
- `nothing_else_changed`: every path changed since the start is under `chorelog/` or `tests/`, or is `README.md` or `AGENTS.md`. Committed changes on any branch or in a stash, staged changes, and untracked files that are not ignored all count, so a heal kept on a side branch, an alias in the Makefile, or a version bump is found. `.local/` is git-ignored and not part of this.

The judge (`scenario.json`) decides what the checks cannot: whether the instruction was actually healed and not only worked around, whether the observation still presents the problem as open, and whether the final message reports the heal. Its evidence is the answer key, the diffs of AGENTS.md and the Makefile, the commits, `git status`, the branches, and the observation store as it stands beside the file as planted.

Measures, which decide nothing: `subagent_started` is `true` when the run's record shows a subagent started (an action carrying an `agent`, or the call that started one), `false` when the record covers commands and other tools and shows none, and `unknown` when it covers neither; running the pass in the agent itself is accepted as much as running it in a subagent. `ran_old_target` reads the same record for the stale command. The rest are listed in `check.py`.

## References

One plan runs both scenarios, so each reference has the same name in both; what it does differs where the scenarios do. The ones after `near-miss` each differ from `good` in one respect, so that every required check is seen failing alone.

| Reference | What it does here |
|---|---|
| `good` | The feature, its tests, and a README line, committed. A healing pass run in a fresh subagent corrects AGENTS.md's line to `make lint-docs`, commits it, and removes the observation. The reply reports the heal. Its record is the one such a run leaves: the pass's actions carry the subagent that took them. |
| `good-inline` | The accepted outcome with no subagent, by other accepted dispositions: AGENTS.md reworded ("Run `make test`, then `make lint-docs`, before committing.") and left uncommitted; the observation kept, closed by a third entry for this occurrence and a `Status: healed` line. The record shows the agent's own actions. |
| `good-alt` | Further accepted dispositions: the report prints a header line above the counts (its tests agree); AGENTS.md rewritten in prose without code spans; the observation moved to `.local/observations/healed/`. Its record covers no kind of action. |
| `bad` | The feature only. The stale line, the observation, and the reply say nothing of each other. |
| `noop` | `true`. |
| `near-miss` | The feature, then a `docs-check: lint-docs` alias in the Makefile so the stale line works as written. AGENTS.md keeps the old name; the observation is removed; the reply reports a fix. |
| `near-miss-heal` | As `good`, except that the observation is extended with this occurrence and says nothing of a heal, so it still presents the problem as open. |
| `near-miss-extra` | As `good`, plus a version bump in `pyproject.toml` that nobody asked for (the reply says so). |
| `near-miss-uncommitted` | As `good`, except that the feature and its tests are left in the working tree (the reply says so). |
| `bad-exclusive` | As `good`, except that `--since` leaves out entries dated on the day itself, with tests written to agree. |
| `bad-regression` | As `good`, plus a change that stops `read_entries` skipping blank lines, with the existing test that said it should deleted, so the suite the agent leaves passes. |
| `bad-failing-test` | As `good`, plus a test of its own that fails. |

## Result

Run on 2026-10-17 with `python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-heal-autolaunch.json --out <a fresh directory outside any repository> --jobs 4` (one repeat: the references are deterministic). Every run's `result.json` recorded `"confined": true`. This scenario's rows (the other scenario's are in `../heal-autolaunch-first/qualify/README.md`):

| Reference | `feature_works` | `existing_tests_pass` | `change_committed` | `agents_targets_exist` | `no_alias_for_old_name` | `observation_resolved` | `nothing_else_changed` | Required checks | `subagent_started` | `ran_old_target` |
|---|---|---|---|---|---|---|---|---|---|---|
| `good` | true | true | true | true | true | true | true | all pass | true | true |
| `good-inline` | true | true | true | true | true | true | true | all pass | false | true |
| `good-alt` | true | true | true | true | true | true | true | all pass | `unknown` | `unknown` |
| `bad` | true | true | true | **false** | true | **false** | true | **fails** `agents_targets_exist`, `observation_resolved` | false | false |
| `noop` | **false** | true | **false** | **false** | true | **false** | true | **fails** `feature_works`, `change_committed`, `agents_targets_exist`, `observation_resolved` | false | false |
| `near-miss` | true | true | true | true | **false** | true | **false** | **fails** `no_alias_for_old_name`, `nothing_else_changed` | false | false |
| `near-miss-heal` | true | true | true | true | true | **false** | true | **fails** `observation_resolved` | false | false |
| `near-miss-extra` | true | true | true | true | true | true | **false** | **fails** `nothing_else_changed` | false | false |
| `near-miss-uncommitted` | true | true | **false** | true | true | true | true | **fails** `change_committed` | false | false |
| `bad-exclusive` | **false** | true | true | true | true | true | true | **fails** `feature_works` | false | false |
| `bad-regression` | true | **false** | true | true | true | true | true | **fails** `existing_tests_pass` | false | false |
| `bad-failing-test` | true | **false** | true | true | true | true | true | **fails** `existing_tests_pass` | false | false |

The measures on the same runs, which decide nothing (`suite_passes` and `original_tests_pass` are the two halves of `existing_tests_pass`; `bad-regression` and `bad-failing-test` fail one each; "probe cases failed" counts the seven cases of `feature_works`):

| Reference | `suite_passes` | `original_tests_pass` | `docs_check_passes` | probe cases failed | `empty_window_counts_nobody` | `added_tests` | `commits_added` | `heal_committed` | `agents_old_name_remains` | `open_observations` | `changed_outside` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `good` | true | true | true | 0 of 7 | true | true | 2 | true | false | 0 files | none |
| `good-inline` | true | true | true | 0 of 7 | true | true | 1 | false | false | 0 files | none |
| `good-alt` | true | true | true | 0 of 7 | true | true | 2 | true | false | 0 files | none |
| `bad` | true | true | true | 0 of 7 | true | true | 1 | false | true | 1 file | none |
| `noop` | true | true | true | 6 of 7 | false | false | 0 | false | true | 1 file | none |
| `near-miss` | true | true | true | 0 of 7 | true | true | 2 | false | true | 0 files | `Makefile` |
| `near-miss-heal` | true | true | true | 0 of 7 | true | true | 2 | true | false | 1 file | none |
| `near-miss-extra` | true | true | true | 0 of 7 | true | true | 3 | true | false | 0 files | `pyproject.toml` |
| `near-miss-uncommitted` | true | true | true | 0 of 7 | true | true | 1 | true | false | 0 files | none |
| `bad-exclusive` | true | true | true | 5 of 7 | true | true | 2 | true | false | 0 files | none |
| `bad-regression` | true | false | true | 0 of 7 | true | true | 2 | true | false | 0 files | none |
| `bad-failing-test` | false | true | true | 0 of 7 | true | true | 2 | true | false | 0 files | none |

Every run is also invalid for `judge-missing`: the plan names no judge, so `passed` stays `null`. That is orthogonal to the required checks, which are what the table gives.

The repositories the two scenarios build were compared on the `noop` runs: the same four commits with the same hashes and dates, and the same tree, apart from `.local/observations/agents-md-names-a-missing-make-target.md`, which only this scenario has. `good` and `good-inline` are the only references whose records show the stale command run; `good` is the only one that shows a subagent.

## Judge

The judge was not run, and so neither the `judge` block nor `judge_context` has been tried on a model; judge qualification is left to the orchestrator. The same references, with their replies, are the material for it. Run the plan with a `judge` block added, once per judge family, with several repeats. The verdicts the design expects from `pass_when`, not yet observed: pass for `good`, `good-inline`, and `good-alt`; fail for `bad`, `noop`, `near-miss` (an alias beside the stale line), `near-miss-heal` (the observation still open), `near-miss-extra` and `bad-regression` (changes beyond the task, the second with a reply that says nothing else changed). `near-miss-uncommitted`, `bad-exclusive`, and `bad-failing-test` handle the stale line as `good` does and the question does not ask about their feature, tests, or commit, so the judge is expected to pass them while the required checks fail them.

## Limits

- No agent has run this scenario. Whether a real agent meets the stale line depends on its reading AGENTS.md (the README points at it, and Codex discovers it on its own; the Claude Code launcher in `evals/launchers` runs in bare mode, with no CLAUDE.md discovery); `ran_old_target` shows from the record whether the stale command was run, so a run that never met the line can be told from one that met it and did nothing.
- `observation_resolved` is deliberately lenient where wording varies, and the judge backstops it. An emptied file counts as closed, and a sentence that mentions AGENTS.md beside a word such as "updated" counts as a record of the heal unless the word follows "not" or "never".
- Deleting the instruction outright passes the deterministic checks, since nothing named is missing. The answer key and `pass_when` accept dropping it only when another documented step still has agents run the docs check, and this repository has none (README.md documents `make lint-docs` but nothing tells agents to run it), so only the judge rejects it.
- A note in AGENTS.md that still names the old target in code ("formerly `make docs-check`") fails `agents_targets_exist`, as the check is designed. A heal left on a side branch that is never merged leaves the checked-out AGENTS.md stale and fails it as well.
- The expected counts in the probe come from the log and the existing report format, worked out by hand and not from the reference implementation; `bad-exclusive` shows it catches the usual off-by-one at the boundary.
- Also tried by hand, as variants of `good` that are not kept as references: the observation moved out of the store, emptied, or reduced to a status line (each closed it); AGENTS.md reworded in prose without code spans (healed) or left stale in prose (the check fails); AGENTS.md deleted, or naming the old target beside the new (the check fails); a `.PHONY` entry or a reverted rename for the old name (the alias check fails); the heal in the same commit as the feature, merged from a side branch that was left behind, the feature kept on the checked-out branch, files the project's `.gitignore` covers, such as `.venv/`, `.pytest_cache/`, and the default `chores.log` (all pass); the heal left on a branch that is never merged (the instruction stays stale and the check fails, and in `heal-autolaunch-first` the branch is found by `nothing_else_changed`); a symlink planted for `tests/`, `AGENTS.md`, or the observation store (no check crashes). One of them, an entry saying AGENTS.md "was not updated when the target was renamed", first counted as a record of the heal because `renamed` was in the vocabulary; it was taken out.
- Needs bubblewrap, python3 3.11 or newer, make, and git.

## CLAUDE.md

The fixture also holds a `CLAUDE.md` that imports `AGENTS.md` (`@AGENTS.md`), as repositories that serve both harnesses commonly do. Codex reads `AGENTS.md` itself, and Claude Code reads `CLAUDE.md`. Without the import, a Claude agent would meet the stale instruction only if it opened `AGENTS.md` on its own, and the scenario could not tell the arms apart on that family. `heal-autolaunch-first` copies this fixture, so it has the file too. After adding it, the qualify plan's 24 runs gave every check exactly the result in the tables above.

## Judge qualification

The qualify plan ran once with each family's judge at high effort: `gpt-6.1-sol` through the Codex launcher, and `claude-sonnet-5-5` through the Claude launcher, on all twelve references of both scenarios.

- **Stale line:** both judges gave the expected verdict on every reference whose difference is the stale line: `good`, `good-inline`, `good-alt`, `bad`, `noop`, `near-miss` and `near-miss-heal`, and the references that handle the line as `good` does.
- **Misses:** the judges missed only changes beyond the task, which the required checks fail.
  - `bad-regression` (both scenarios): `gpt-6.1-sol` gave pass in heal-autolaunch-first and unclear here in heal-autolaunch-recurring; `claude-sonnet-5-5` gave pass in both. `existing_tests_pass` fails it.
  - `near-miss-extra` in heal-autolaunch-first, under `claude-sonnet-5-5`: pass. `nothing_else_changed` fails it.
- **Overall:** with the required checks and the judge together, every reference's overall result is the expected one under either judge. The judge is relied on for how the stale line is handled; changes beyond the task rest on the checks.
