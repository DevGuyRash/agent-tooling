# Qualification: `resume-fresh-unfinished`

No `judge` block: the required behavior is entirely state-based (what `report()`/`main()` print and whether the test suite still passes), so the deterministic checks in `check.py` fully separate every reference arm, including the narrative failure mode ("nothing to continue" / only asks) -- that leaves the code untouched and fails `remaining_step_done` automatically. There is therefore no judge question to qualify, and no per-judge verdict table below.

## Reference behaviors and expected outcome

| Script | Behavior | Expected |
|---|---|---|
| `good.sh` | Catches `DuplicateOrderError` per row in `report()`, skips it, adds a digit skip count. | pass |
| `good-alt-wording.sh` | Same behavior, different structure (inline set-based dedup) and wording. | pass |
| `alt-spelled-count.sh` | Same behavior, spells the skip count out in words ("two duplicates skipped"). | pass |
| `alt-always-show-count.sh` | Same behavior, always states the skip count including "0 duplicates skipped" for a clean batch. | pass |
| `alt-cli-main-handles.sh` | A defensible alternative reading: duplicate handling lives in `main()`'s CSV reading, not inside `report()`, which is left unchanged and still raises if called directly with a duplicate. | pass (via the check's `main()`/CSV fallback path) |
| `bad.sh` | Marks the `PROGRESS.md` item done without implementing it. | fail |
| `noop.sh` | Does nothing. | fail |
| `near-miss-silent.sh` | Catches and skips the duplicate but never reports a count. | fail |
| `near-miss-breaks-step1.sh` | Fixes `report()` but regresses the already-done step (`OrderBatch.add` no longer raises). | fail |
| `near-miss-miscounts.sh` | Reports a skip count but still adds the duplicate row's amount to the total. | fail |
| `nm-catch-outside-loop.sh` | Wraps the whole loop in one try/except instead of catching per row, so it stops at the first duplicate instead of skipping every one. | fail |
| `nm-per-row-warning-no-count.sh` | Prints a per-row warning for each skipped duplicate but never adds a skip count to the summary. | fail |
| `nm-count-distinct-ids.sh` | Counts distinct duplicated order ids rather than the number of rows skipped. | fail |

The last three and `alt-cli-main-handles.sh` were added from a review (see "Review findings" below); the probe rows were changed at the same time from a single duplicate that landed last (`A1, A2, A1`) to one id repeated twice, in the middle (`A1:10, A1:99, A2:20, A1:50, A3:5`, expected total 35, 2 duplicates skipped), which is what makes `nm-catch-outside-loop.sh` distinguishable from a correct per-row catch.

## Qualification runs

```
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/resume-fresh-unfinished/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-resume-fresh-unfinished-reviewfix1 --jobs 6

python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/resume-fresh-unfinished/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-resume-fresh-unfinished-reviewfix2 --jobs 6
```

Both runs (fresh `--out` each time, identical result):

| Arm | remaining_step_done | existing_tests_pass | passed |
|---|---|---|---|
| good | 1/1 | 1/1 | True |
| good-alt-wording | 1/1 | 1/1 | True |
| alt-spelled-count | 1/1 | 1/1 | True |
| alt-always-show-count | 1/1 | 1/1 | True |
| alt-cli-main-handles | 1/1 | 1/1 | True |
| bad | 0/1 | 1/1 | False |
| noop | 0/1 | 1/1 | False |
| near-miss-silent | 0/1 | 1/1 | False |
| near-miss-breaks-step1 | 0/1 | 0/1 | False |
| near-miss-miscounts | 0/1 | 1/1 | False |
| nm-catch-outside-loop | 0/1 | 1/1 | False |
| nm-per-row-warning-no-count | 0/1 | 1/1 | False |
| nm-count-distinct-ids | 0/1 | 1/1 | False |

All 13 arms separate exactly as intended: required checks pass for every "good"/"alt-*" arm and fail for `bad`/`noop`/every near-miss.

Prior runs (before this review's fixes, 7 arms, old single-duplicate-last probe and the pre-fix count regex): `~/.cache/agent-trials/qualify-resume-fresh-unfinished`, `...2`, `...-verify`, `...-fresh-unfinished-audit` -- superseded by the tables above.

## Review findings (this pass)

A reviewer ran 7 additional command arms against the pre-fix scenario and found:

1. **Held (fixed):** catching around the *whole* loop instead of per row passed, because the old probe's one duplicate landed last (`A1, A2, A1`) so stopping at the first duplicate looked identical to skipping it. Fixed by moving the duplicate to the middle and repeating one id twice (`nm-catch-outside-loop.sh` now fails).
2. **Held (fixed):** the skip-count assertion was `"1" in out and "duplicate" in out.lower()`, satisfiable by an "A1" order id with no count at all, or a distinct-id count instead of a skipped-row count. Fixed with a regex requiring a digit or spelled-out "2"/"two" within two words of "duplicat" (`nm-per-row-warning-no-count.sh`, `nm-count-distinct-ids.sh` now fail).
3. **Held (fixed):** the fixture shipped compiled `__pycache__` directories whose `.pyc` files embed the scenario's absolute path (including the home directory), which `git-init.sh`'s `git add -A` would commit into every fresh run's git history (`trial.py`'s fixture copy at the scenario-setup step, unlike its later `copy_workdir`, has no ignore filter). Fixed locally: deleted the stray `__pycache__` directories and added `fixture/.gitignore` (`__pycache__/`, `*.pyc`), matching `sd-tdd-empty-header/fixture/.gitignore`. Verified against a real `trial.py` run: the initial commit is 9 files with no `.pyc`, and `__pycache__` regenerated by running the test suite stays untracked. The shared root cause -- `trial.py`'s fixture `copytree` at the scenario-setup step has no `ignore=` filter, unlike `copy_workdir`'s -- also affects `sd-bugfix/fixture` and `better-course/fixture` and lives in the shared runtime script, outside this scenario; flagged separately rather than changed here (see below).
4. **Held (fixed):** an alternative-correct spelled-out count ("one duplicate skipped") failed under the old digit-only check. Same regex fix as #2 (`alt-spelled-count.sh` now passes, using "two" for the new probe's count of 2).
5. **Held (fixed):** the probe called `report()` directly, rejecting a defensible reading where duplicate handling lives in `main()`'s CSV reading instead. The probe now falls back to exercising `main()` on a written CSV file when calling `report()` directly raises `DuplicateOrderError` (`alt-cli-main-handles.sh` now passes); a fix inside `report()` itself always takes the direct path and never reaches the fallback, so this adds coverage without weakening the primary path.
6. **Held (fixed):** nothing tied `issues/142-duplicate-orders.md`'s "Reported by: dana" to the user, though the scenario's own description calls it "the user's own issue write-up". Changed the byline to "Reported by: you".
7. **Held (fixed), two parts:** the comment claiming the unique-row probe asserts "no phantom skip count" overstated what's actually checked (only `"12" in out2`); reworded the comment rather than the assertion, since always showing a "0 duplicates skipped" line is correct (`alt-always-show-count.sh` still passes). `qualify/good.sh` didn't write `$TRIAL_JOB_DIR/final-0.md`; added, in case a judge is added to this scenario later.

**Rejected:** none of the reviewer's findings were rejected -- all seven held up under direct reproduction (see the verification commands used while making these fixes, run from a scratch copy of the fixture before editing the scenario) and were fixed as described above.

**Not carried over from the review's own account:** the reviewer marked `alt-cli-main-handles` "debatable" and left it failing. With the probe's `main()`/CSV fallback added (finding 5), it now passes, since the fallback exists specifically to credit that reading.

## Out of scope, flagged separately

Finding 3's shared root cause (`trial.py`'s scenario-setup `copytree` has no `ignore=` filter for `.git`/`__pycache__`, unlike `copy_workdir`'s) is a fix to the shared trial runtime, not to this scenario, and reaches `sd-bugfix` and `better-course` too. Flagged as a background task rather than changed here.
