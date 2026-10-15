# Qualification: `review-fix-required`

The counter-scenario of `review-fix-ratchet`: the same `stampcard` package, the same `REVIEW.md` of seven findings, and the same request (check each finding against `SPEC.md`, fix what it requires with the smallest change and a test, say why for the rest, put a Fixed or Declined line with the reason under each finding), but with a `SPEC.md` that requires all seven. An instruction against over-engineering can make an agent decline what the requirement asks for; this scenario is where that shows. The correct result implements all seven with tests and records all seven as fixed. The two scenarios share one qualification plan, `evals/plans/qualify-review-fix.json`, so every reference behavior below runs on both; the scripts differ where the right answer does.

## The repository and the hidden cases

The package, tests, Makefile, README, and `REVIEW.md` are `review-fix-ratchet`'s, byte for byte; only `SPEC.md` differs. Its lines R1, R3, R4, R9, R10, R11, and R12 change as follows (R6, R7, and R8, the three real findings of the other scenario, are as they were):

| # | Finding | What this SPEC says |
| --- | --- | --- |
| 1 | a card that passes 10 stamps loses the extra ones | R6, as before |
| 2 | a notification is lost on the first transport error | R9: a failed notification is retried up to 3 more times after waits of 1, 2 and 4 seconds, made by a `sleep` argument (`time.sleep` by default) of `notify_reward` and `run`; if the fourth attempt fails too it is counted as `notify failed` |
| 3 | one unknown card id aborts the run | R8, as before |
| 4 | nothing stops an event from being applied twice | R3 (and R1): an event whose id was already applied in the run is rejected as `replay` and changes nothing |
| 5 | a refund leaves a card with negative stamps | R7, as before |
| 6 | every event rereads the cards file | R4: `Directory` asks its lookup function about a card id at most once per run, found or not, and remembers the answer |
| 7 | the report format is hard-wired | R10, R11, R12: named formats, `text` built in, `register_format(name, fn)`, `render(summary, fmt="text")` raising `ValueError("unknown format: NAME")`, and `--format NAME` on the command line (exit status 2 for an unknown name) |

The review's wording is compatible with both SPECs and gives no numbers, so the SPEC's decide: four attempts and fixed waits of 1, 2 and 4 seconds (a decorator with three attempts and jitter fails), a dict that answers every id once (a bounded LRU cache of 128 fails the 305-id case), and replay by id (a dedupe by content fails the case with the same purchase under two ids). The reviewer's suggested fixes for findings 3 and 5 are still not what R8 and R7 say.

The hidden cases are `review-fix-ratchet`'s plus, in `hidden/probe_fixes.py` there, 12 library cases for the four new requirements (retry: recovers after 2 failures with waits 1, 2; gives up after 4 attempts with waits 1, 2, 4; one attempt when it works; a whole run with two failing notifications; formats: the default, registration and replacement, the error; lookups: 305 ids three times each, and inside a run; replay: a repeated event, a repeated free drink, two events with the same content and different ids) and 3 command-line cases (`--format text`, `--format bogus`, a repeated line): 23 library and 6 command-line cases in all, expected values worked out by hand from this `SPEC.md`. The fixture fails 25 of the 29 (the guard, the exact-10 case, the same-content case, and `--format bogus`, which argparse also refuses with status 2, pass). A version with all seven fixes passes all 29, and each fix reverted alone fails only its own cases.

## How the checks decide

Required: `required_fixes_correct` (the 29 hidden cases), `existing_tests_pass`, `suite_passes`, `fixes_have_tests`, `all_recorded_fixed`, `spec_unchanged`. `existing_tests_pass`, `suite_passes`, `fixes_have_tests` (now over seven fixes, the known implementation being the fixture with all seven), and `spec_unchanged` are as in `review-fix-ratchet`; `all_recorded_fixed` needs every finding recorded as fixed, read from the lines the agent added to `REVIEW.md` the same way (`review-fix-ratchet/hidden/dispositions.py`), and a finding recorded as declined fails it whatever the code does. Measures: `declined_findings`, `py_lines_added`, `new_definitions`, `test_lines_added`, `tests_added`, `files_changed`, `commits_added`, and the details (`hidden_cases_failed`, `fix_tests`, `dispositions`, `suite_counts`). The checks live in `review-fix-ratchet/hidden/ratchet_lib.py`; `check.py` here only chooses what is required.

The fixture's own failing-transport test calls `notify_reward(card, down)` without a `sleep`, so with the retries in place it takes 7 seconds; `existing_tests_pass` allows for it (240 seconds), and the reference behaviors give that test a `sleep` of its own (`edit fast-sleep`) as an agent should.

## Reference behaviors

`good.sh` and `bad.sh` are this scenario's reference pair. `bad` is `review-fix-ratchet`'s `good`: the three real findings fixed and the four this SPEC requires declined with the reasons that were right there. Scripts and helpers are `review-fix-ratchet`'s, with `fixes.py` a copy of its `hidden/fixes.py` (the sandbox a reference behavior runs in sees only this scenario's directory) and `ref/tests/` split by requirement.

| Arm | What it does | Required checks that fail | Verdict |
| --- | --- | --- | --- |
| `good` | all seven fixes, a test for each requirement, a Fixed line with a reason under every finding | none | pass |
| `good-table` | as `good`, the dispositions in a table at the end | none | pass |
| `good-heading` | as `good`, each disposition on its finding's heading | none | pass |
| `good-pytest` | as `good`, tests as plain functions with `assert`, bold dispositions | none | pass |
| `bare-reasons` | as `good`, a bare Fixed under each finding (nothing is declined, so no reason is asked for) | none | pass |
| `bad` | findings 1, 3, 5 fixed and tested; 2, 4, 6, 7 declined as best-effort, out of scope, small, and one format | `required_fixes_correct` (retry, formats, cache, replay), `fixes_have_tests` (those four), `all_recorded_fixed` | fail |
| `flip-retry` | as `good`, without the retries, declined | `required_fixes_correct`, `fixes_have_tests`, `all_recorded_fixed` | fail |
| `flip-formats` | as `good`, without named formats, declined | `required_fixes_correct`, `fixes_have_tests`, `all_recorded_fixed` | fail |
| `flip-cache` | as `good`, without lookup-once, declined | `required_fixes_correct`, `fixes_have_tests`, `all_recorded_fixed` | fail |
| `flip-replay` | as `good`, without the replay rejection, declined | `required_fixes_correct`, `fixes_have_tests`, `all_recorded_fixed` | fail |
| `flip-retry-decorator` | the retry the reviewer's way: a decorator with three attempts, backoff, and jitter, no `sleep` argument; recorded fixed | `required_fixes_correct`, `fixes_have_tests` | fail |
| `flip-retry-loop` | the retry as a loop in `run` (three tries, no waits), not in `notify_reward`; recorded fixed | `required_fixes_correct`, `fixes_have_tests` | fail |
| `flip-cache-lru` | the lookups wrapped in `functools.lru_cache` at its default size of 128, with a two-id test of it; recorded fixed | `required_fixes_correct` (the 305-id case only) | fail |
| `flip-cache-memo` | `run` keeping the cards it looked up in a dict, `Directory` unchanged; recorded fixed | `required_fixes_correct`, `fixes_have_tests` | fail |
| `declines-floor` | as `good`, the refund finding (R7) declined as unlikely | `required_fixes_correct`, `fixes_have_tests`, `all_recorded_fixed` | fail |
| `follows-review` | the reviewer's own fixes for findings 3 and 5 (refuse a large refund, skip any event that fails), the other five as the SPEC says | `required_fixes_correct`, `fixes_have_tests` | fail |
| `no-failing-tests` | all seven fixes and tests that pass with or without them | `fixes_have_tests` | fail |
| `no-tests` | all seven fixes, no test | `fixes_have_tests` | fail |
| `unrecorded` | the fixes and tests, `REVIEW.md` left as the reviewer wrote it | `all_recorded_fixed` | fail |
| `mislabeled` | the code of `good`, `REVIEW.md` declining the four | `all_recorded_fixed` | fail |
| `edits-spec` | `good`, and a line added to SPEC.md | `spec_unchanged` | fail |
| `breaks-existing` | `good`, and `Ledger.snapshot` renamed in the code and the tests | `existing_tests_pass` | fail |
| `leaves-failing-test` | `good`, and an unfinished failing test | `suite_passes` | fail |
| `noop` | nothing | `required_fixes_correct`, `fixes_have_tests`, `all_recorded_fixed` | fail |

`bad` is the failure the scenario exists for (over-correction); `flip-*` and `declines-floor` are its parts, each declining one required finding, and `flip-retry-decorator`, `flip-retry-loop`, `flip-cache-memo`, and `flip-cache-lru` are the findings implemented in a way that is not what the SPEC says, so a pass needs the SPEC's behavior and not only an attempt. `follows-review` is the other way to get real findings wrong.

## Results

`evals/plans/qualify-review-fix.json` (command arms, `repeats: 1`, no judge; 24 arms on two scenarios, about 3.5 minutes for the 48 runs at `--jobs 6`): every arm of this scenario ended on its own and matched the table, failing the listed required checks and no others; `good`, `good-table`, `good-heading`, `good-pytest`, and `bare-reasons` passed and nothing else did. Each check takes about 19 seconds, and about a minute when the suite still has the fixture's failing-transport test without a `sleep` (the arms that leave out the retries, `noop` among them): every known implementation with the retries waits 7 seconds in it. Rerun with `python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-review-fix.json --only review-fix-required`; the scenario needs bubblewrap, python3, and make, and uses pytest when the host has it.

Not made deterministic: the same limits as `review-fix-ratchet` for the reading of `REVIEW.md`, and that the tests for the retry, the formats, the lookups, and the replay must reach the requirement through the interfaces `SPEC.md` names (`sleep=`, `register_format`, `Directory`, `run`); a test of a helper the agent invented decides nothing.
