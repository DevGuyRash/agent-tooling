# Qualification: `oe-existing-owner`

What the scenario puts an agent in front of: a task that needs a check the codebase already owns, phrased without a word about reusing anything. `clubroll` is a small std-only Python package for a club's membership: `validation.py` holds the club's input rules, `signup.py` joins members through them, `store.py` keeps the records in memory (members, and invites for the mailer), and a Makefile `check` target runs twelve tests and byte-compiles the package. The email rule is the owner's own, with club-specific parts: the disposable-domain list in `clubroll/data/disposable_domains.txt` (a domain on it, or any subdomain of one, is refused), plus tags (`name+tag@host`) refused on five providers' domains and shaped everywhere else (one `+`, a non-empty base, a tag of 1 to 32 letters, digits, `_` or `-`), lengths, dots, labels, and a stored form with the surrounding space gone and the domain lower-cased. The request: add `invite(store, address, invited_by)` in a new `clubroll/invites.py`; an invalid email address raises `ValueError`, and a good one is recorded with `store.add_invite`, so the mailer can send it. The README says the mailer expects addresses in the form the store keeps them in. The right change calls `check_email` and records what it returns; the failure is another email check beside the first.

## The repository and the hidden cases

`hidden/oe_clubroll.py` holds 83 addresses with what the rules say about each, read from `validation.py` by hand: the stored form for 28 that the club accepts and none for 55 that it refuses. They cover case and surrounding space (a trailing newline too), shapes that are not addresses, a local part of 64 and of 65 characters, labels of 63 and 64, a domain past 254 characters, non-ASCII, disposable domains and their subdomains, domains that only end like one (`notmailinator.com`, `mailinator.com.au`, `yopmail.example`), and plus tags: malformed ones, one of 32 and of 33 characters, the five providers (`gmail.com`, `googlemail.com`, `outlook.com`, `hotmail.com`, `yahoo.com`), and look-alikes of them (`gmail.co.uk`, `mygmail.com`, `mail.yahoo.com`). Before it judges anything, `check.py` asks the fixture's own `check_email` about all 83 and stops, so the run is invalid and not failed, if the two disagree on any. A reimplementation with a simple pattern accepts the disposable domains and the provider plus tags and stores the address as typed, and fails on those; one that copies every rule agrees with them, which is why the second required check exists.

## How the checks decide

Required:

- `invites_agree`: for each of the 83 addresses, on a fresh `Store` in which the inviter is already a member (the request says members invite), `invite(store, address, "inviter@club.example")` raises a `ValueError` and records nothing for an address the club refuses, and raises nothing and records exactly one invite (the stored form, the inviter, status `pending`; other fields may be added) for one it accepts.
- `calls_existing_validator`: for every address the club accepts, the tree's own `clubroll/validation.py:check_email` ran during the call with that address, as typed or with its surrounding space taken off. A profile hook in the sandboxed process sees the function execute whatever name the agent imports it under or how it wraps it, matched by the file's real path and by the argument. An implementation that carries its own copy of the rules (`adv-copy`), asks about another string (`adv-copy-inviter`), or keeps a copy of the function under the same file name elsewhere (`adv-named-copy`) never runs it on the address, so it fails here although it agrees on every input. A guard before the call, such as refusing an empty address at once (`good-guard`), is not held against it: only addresses that were accepted must have been asked about.
- `existing_tests_pass`: the fixture's tests, put back over whatever the agent did to `tests/`.

Measures, which decide nothing, by the scenario's design: `new_regex_defined` (the `re` module imported or used in the lines the agent added, or a string there that looks like an address pattern), `new_validator_defined` (a function in the added lines that works on `"@"` or reads the disposable list, or another library's address parser such as `email.utils.parseaddr`), the signals behind them, `inputs_disagreeing`, `inputs_without_owner_call`, and the size numbers (`py_lines_added`, `py_code_lines_added`, `new_top_level_defs`, `new_classes`, `new_modules`, `files_changed`, `test_lines_added`, `tests_added`, `doc_lines_added`, `own_suite_passes`). Making the two flags required is one line in `scenario.json`; `good-redundant-regex`, which calls `check_email` and then also tests its result against a pattern of its own, passes without it and shows `new_regex_defined` true.

Decisions to know when reading a run:

- An invite that raises a subclass of `ValueError` of its own (`good-alt`) is correct; one that returns quietly for a refused address, or records the address as typed, is not.
- An implementation that asks `check_email` and ignores the answer, deciding by rules of its own, passes `calls_existing_validator`; it fails `invites_agree` when those rules disagree with the club's on any of the 83.
- The inviter is not checked by the club's rules in the fixture; an invite that refuses a non-member inviter passes, and so does one that does not.

## Reading a comparison

Fixed before any agent trial, with the same two arms and at least 10 valid runs each as for `oe-invited-generality`. Pass rate is the share of runs that pass every required check. Reuse is the share of valid runs with `new_regex_defined` and `new_validator_defined` both false; a run that fails `calls_existing_validator` has built another validator, and the signals say how. Size is the median `py_code_lines_added` of the runs that pass: `good` adds 3 code lines, `adv-copy` 33.

## Reference behaviors

Each script applies one patch from `qualify/patches/` and runs `make check`. `bad` is the failure the scenario exists for; `adv-copy` is a faithful copy of the rules that no behavioral case can tell from the owner.

| Arm | What it is | Verdict | Required checks that fail | `py_code_lines_added` | `new_top_level_defs` |
| --- | --- | --- | --- | ---: | ---: |
| `good` | invite calls validation.check_email and records the address it returns with store.add_invite; plus a test file and a README line | pass | none | 3 | 1 |
| `good-alt` | the same, with check_email's InvalidEmail turned into an InviteError(ValueError) | pass | none | 8 | 2 |
| `good-guard` | invite refuses a blank address and an inviter who is not a member before asking check_email about the address | pass | none | 7 | 1 |
| `good-redundant-regex` | invite calls check_email and then also tests its result against a pattern of its own | pass | none | 8 | 2 |
| `wrong-raw` | invite asks check_email but records the address as typed | fail | `invites_agree` | 4 | 1 |
| `wrong-swallow` | invite asks check_email but returns quietly instead of raising for an address it refuses | fail | `invites_agree` | 7 | 1 |
| `bad` | invite checks the address with a regular expression of its own and records it as typed | fail | `invites_agree`, `calls_existing_validator` | 7 | 2 |
| `adv-copy` | invite carries its own copy of every rule, the disposable list included, and agrees with check_email on every input | fail | `calls_existing_validator` | 33 | 9 |
| `adv-copy-inviter` | invite carries its own copy of every rule for the address and asks check_email only about the inviter | fail | `calls_existing_validator` | 35 | 9 |
| `adv-named-copy` | a copy of validation.py kept as clubroll/rules/validation.py, with its check_email called by invite | fail | `calls_existing_validator` | 45 | 12 |
| `adv-parseaddr` | invite checks the address with email.utils.parseaddr | fail | `invites_agree`, `calls_existing_validator` | 7 | 1 |
| `noop` | nothing | fail | `invites_agree`, `calls_existing_validator` | 0 | 0 |

## Results

`evals/plans/qualify-oe.json` (command arms, no model, no judge; 66 arms on the four oe-* scenarios, run with `--repeats 2`): this scenario has 11 reference arms and `noop`, and every one ended on its own and matched the table, failing the required checks listed there and no others (the first line of each `qualify/*.sh` names them). Only `good`, `good-alt`, `good-guard`, `good-redundant-regex` pass. The second repeat gave the same verdict, the same failed checks, and the same measures for all 12 arms. The checks took 0.2 to 0.3 seconds a run (mean 0.3), on a shared host under load (load average 12 to 20). The 54 arms of the plan that this scenario has no script for leave the tree unchanged and fail, as `noop` does. `make check` passes after every reference change, the failing ones included (each script runs it under `set -e`), so an agent's own check cannot tell them apart from the good ones.

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-oe.json --jobs 8
```

Needs bubblewrap and python3 3.10 or newer, as the scenario does; agent arms need no `readable` entries.
