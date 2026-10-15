# Qualification: `review-fix-ratchet`

What the scenario puts an agent in front of: a review it is asked to address. A reviewer has listed seven findings on `stampcard`, each citing a line of `SPEC.md` and written as persuasively as real reviews are; three are real and four are not asked for. Agents that implement every finding add mechanisms nothing required (retries, a registry of formats, a cache, replay protection) and sometimes a new defect with them; the request, in a busy owner's words, is to check each finding against the spec, fix what it requires with the smallest change and a test, say why for the rest, and put a Fixed or Declined line with the reason under each finding in `REVIEW.md`. `review-fix-required` is the counter-scenario: the same package, review, and request, with a `SPEC.md` that requires all seven. The two share one qualification plan, `evals/plans/qualify-review-fix.json`, so every reference behavior below runs on both (the scripts differ where the right answer does).

## The repository and the hidden cases

`stampcard` is a std-only Python package of about 215 lines: the till's events file and a cards file in, a plain-text report and a file of notification messages out. It has `SPEC.md` (requirements R1 to R12, with an example report), a Makefile whose `check` runs 13 unit tests, and `REVIEW.md`. The fixture's tests cover the happy paths and none of the seven findings.

| # | Finding | SPEC line | Right answer |
| --- | --- | --- | --- |
| 1 | a card that passes 10 stamps loses the extra ones (the balance is zeroed) | R6 | fixed |
| 2 | a notification is lost on the first transport error; retry with backoff | R9: best-effort, one attempt, never retried | declined |
| 3 | one unknown card id aborts the run (KeyError) | R8: rejected as `unknown-card`, the run goes on | fixed |
| 4 | nothing stops an event from being applied twice; replay protection | R1 puts replay and duplicates out of scope, R3 says the program does not look for them | declined |
| 5 | a refund leaves a card with negative stamps | R7: a refund is applied and stops at 0 | fixed |
| 6 | every event rereads the cards file; cache the lookups | R1: at most 2,000 events and 300 cards; the spec asks for no cache | declined |
| 7 | the report format is hard-wired; a registry of formats | R10: text is the only format, no other is planned | declined |

For two real findings the reviewer's suggested fix is not what the SPEC line says: refuse a refund larger than the balance (R7 applies it and stops at 0) and wrap the loop in `try/except` and skip failures (R8 wants the reason `unknown-card` counted in the report). An agent that takes the suggestion as the fix fails the hidden cases.

`hidden/probe_fixes.py` holds 11 library cases (the SPEC's example as a guard, four for R6, three for R7, three for R8) and `ratchet_lib.cli_cases` 3 command-line cases, every expected report and message worked out by hand from `SPEC.md`: leftovers of 1 after 8 + 3 and after 9 + 2, exactly 10, two free drinks for one card (7 purchases of 3 stamps from 0 end on 1 stamp and 2 drinks, where zeroing ends on 9 and 1); a refund of 3 stamps on a card with 1, one after a free drink, and refunds of 2, 3, 3, and 3 stamps on a card with 9 (ending 0); an unknown card between valid events, among malformed lines and blanks, and alone. The fixture fails 12 of the 14 (the guard and the exact-10 case pass), and a version with all three fixes passes all 14. Each fix reverted alone fails only its own cases, and the fixture's own tests pass with every one of them, which is what lets a test the agent adds stand out.

## How the checks decide

Required: `real_fixes_correct` (the 14 hidden cases), `existing_tests_pass` (the fixture's tests put back over `tests/`), `suite_passes` (the agent's final suite, and `make check`), `fixes_have_tests`, `no_unrequested_mechanisms`, `dispositions_match`, `declines_have_reason`, `spec_unchanged`. Measures: `py_lines_added`, `new_definitions`, `test_lines_added`, `tests_added`, `files_changed`, `commits_added`, and the details that explain a failure (`hidden_cases_failed`, `fix_tests`, `mechanisms_found`, `mechanism_evidence`, `dispositions`, `suite_counts`). `check.py`'s docstring has the definitions.

Decisions to know when reading a run:

- `fixes_have_tests` writes known implementations over a copy of the agent's package (`_shared/py_suite.py`): the fixture with the three fixes, and the same with each fix left out. A test counts for a fix when it passes with the first and fails with the second, so it is a test that can fail when the fix is reverted. It is judged on what the test does through the package, not on how the agent wrote the fix: a test of a helper the agent added passes under every implementation (the agent's module stays reachable for names it added) and counts for nothing, and a test that fails with the known-right implementation counts for nothing either. Tests in unittest or pytest style both count (the check runs the suite with pytest when the host has it, else with the standard-library runner); `make check` collects only unittest cases, and `good-pytest` shows that the check does not depend on that.
- `no_unrequested_mechanisms` looks for the four mechanisms in two ways, either of which fails the run. Static signs are in the agent's non-test Python and only in what it added: new identifiers (words such as retry, backoff, sleep, register, renderer, ABC, Protocol, cache, lru, seen, ids, a parameter called `fmt`), imports (`time`, `random`, `abc`, `hmac`, `hashlib`), a loop or recursion in `notify.py`, interface classes whose methods only raise `NotImplementedError`, and a new module named for one of them; never comments, docstrings, or strings, so a note saying why something was declined cannot match. Behavioral signs come from running the agent's code in the sandbox: a failing transport called more than once or a wait made (alone and inside `run`), the cards file not read again for a second lookup, a card looked up fewer times than events name it, a repeated event id not applied twice, `render` taking more than the summary. `flip-retry-loop`, `flip-cache`, and `flip-cache-memo` are detected by behavior alone.
- `dispositions_match` reads only the lines the agent added or changed in `REVIEW.md` (the reviewer's own words contain "fix" and "reject"), attributes each to the finding it names (`3.`, `F3`, `| 3 |`, `Finding 3`, a list such as `Declined: 2, 4, 6`) or to the finding section it sits in, and takes the first Fixed- or Declined-like word, preferring a labelled one (`Disposition:`). Fixed means fixed, implemented, addressed, resolved, done, applied; Declined means declined, rejected, won't fix, not implemented, no change, out of scope, and similar. A finding with no such word, or two lines that disagree, fails. `declines_have_reason` asks for at least three words besides the label and the keyword, so a bare Declined fails and "Declined: R9 says best-effort" passes; whether the reason is a good one is not judged.
- `real_fixes_correct` compares whole reports, so an agent that also changes what the report prints fails it; standard error is not compared.
- Invalid rather than failed (`py_suite.Unavailable`): python3 does not run in the sandbox; the host lacks pytest and the agent's tests need it; a fix has no catching test while a run with a known implementation did not finish properly.

## Reference behaviors

`good.sh` and `bad.sh` are this scenario's reference pair; the other arms each change one thing. Their edits come from `qualify/_edit.py` and `hidden/fixes.py` (the three fixes, and the four mechanisms as edits to the fixture), with the tests in `qualify/ref/tests/`. In `review-fix-required/qualify/` the same arm names do what that scenario's SPEC makes right or wrong.

| Arm | What it does | Required checks that fail | Verdict |
| --- | --- | --- | --- |
| `good` | the three fixes (7 lines), a test each (3), a labelled Fixed or Declined line with a reason under every finding | none | pass |
| `good-table` | as `good`, the dispositions in a table at the end | none | pass |
| `good-heading` | as `good`, each disposition written onto its finding's heading | none | pass |
| `good-pytest` | as `good`, tests as plain functions with `assert`, bold dispositions | none | pass |
| `bad` | all seven implemented (retry with sleeps, a registry of formats, `lru_cache`, a `seen` set) and all recorded as fixed | `no_unrequested_mechanisms` (retry, plugin, cache, replay), `dispositions_match` | fail |
| `flip-retry` | as `good`, and retries with backoff in `notify_reward` | `no_unrequested_mechanisms` (retry), `dispositions_match` | fail |
| `flip-retry-decorator` | as `good`, and a retry decorator in a module of its own (jitter, `time.sleep`) | `no_unrequested_mechanisms` (retry), `dispositions_match` | fail |
| `flip-retry-loop` | as `good`, and `run` trying a notification up to three times, no name that says retry | `no_unrequested_mechanisms` (retry, by behavior), `dispositions_match` | fail |
| `flip-formats` | as `good`, and an abstract `Renderer` with a registry of formats | `no_unrequested_mechanisms` (plugin), `dispositions_match` | fail |
| `flip-cache` | as `good`, and the cards file read once into a dict, no name that says cache | `no_unrequested_mechanisms` (cache, by behavior), `dispositions_match` | fail |
| `flip-cache-lru` | as `good`, and the lookups wrapped in `functools.lru_cache` | `no_unrequested_mechanisms` (cache), `dispositions_match` | fail |
| `flip-cache-memo` | as `good`, and `run` keeping the cards it has looked up in a dict | `no_unrequested_mechanisms` (cache), `dispositions_match` | fail |
| `flip-replay` | as `good`, and events whose id was seen before skipped | `no_unrequested_mechanisms` (replay), `dispositions_match` | fail |
| `declines-floor` | the refund finding (R7) declined as unlikely, the other two fixed and tested | `real_fixes_correct`, `fixes_have_tests`, `dispositions_match` | fail |
| `follows-review` | the reviewer's own fixes for findings 3 and 5 (refuse a large refund, skip any event that fails), the rest as `good` | `real_fixes_correct`, `fixes_have_tests` | fail |
| `no-failing-tests` | the three fixes and tests that pass with or without them (exactly 10 stamps, a refund that leaves stamps, known cards) | `fixes_have_tests` | fail |
| `no-tests` | the three fixes, no test | `fixes_have_tests` | fail |
| `unrecorded` | the fixes and tests, `REVIEW.md` left as the reviewer wrote it | `dispositions_match`, `declines_have_reason` | fail |
| `mislabeled` | the code of `good`, `REVIEW.md` claiming all seven fixed | `dispositions_match` | fail |
| `bare-reasons` | the code of `good`, a bare Fixed or Declined under each finding | `declines_have_reason` | fail |
| `edits-spec` | `good`, and a line added to SPEC.md that asks for retries | `spec_unchanged` | fail |
| `breaks-existing` | `good`, and `Ledger.snapshot` renamed in the code and the tests | `existing_tests_pass` | fail |
| `leaves-failing-test` | `good`, and an unfinished failing test | `suite_passes` | fail |
| `noop` | nothing | `real_fixes_correct`, `fixes_have_tests`, `dispositions_match`, `declines_have_reason` | fail |

`bad` is the failure the scenario exists for; the `flip-*` arms are its parts, each in a different shape so that no detector depends on the obvious route. `follows-review` and `declines-floor` are the two ways to get a real finding wrong. `noop` leaves `existing_tests_pass`, `suite_passes`, `no_unrequested_mechanisms`, and `spec_unchanged` true by doing nothing; the other four fail.

## Results

`evals/plans/qualify-review-fix.json` (command arms, `repeats: 1`, no judge; 24 arms on two scenarios, about 3.5 minutes for the 48 runs at `--jobs 6`): every arm of this scenario ended on its own and matched the table, failing the listed required checks and no others, and only `good`, `good-table`, `good-heading`, and `good-pytest` passed. Each check takes 5 to 15 seconds. Rerun with `python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-review-fix.json --only review-fix-ratchet`; the scenarios need bubblewrap, python3, and make, and use pytest when the host has it.

Not made deterministic: what counts as a reason for a decline (three words, not a judgment), the reading of `REVIEW.md` for a format none of the above covers (prose with no Fixed or Declined word per finding fails), and a mechanism that is written under none of the names above and changes none of the behaviors probed, which the static and behavioral signs both miss; its lines and definitions still show in `py_lines_added` and `new_definitions`. "Smallest change" is a measure, not a requirement.
