# Review of feature/overdue-notices

Read against SPEC.md R6 to R11. The branch is small and its tests pass, but it leaves two cases untested and adds three things the spec never asks for.

## Findings

### 1. No test for equal-day loans

Nothing covers loans with the same number of days, so the order of ties is untested. Add a test with two loans on the same day count and pin the order R8 gives.

### 2. No test for a notice total with a cap or a discount

The notice test only has a standard member under the cap. Add a test with a supporter and one with a loan capped at the tool's replacement value.

### 3. A rule registry for a single rule - `toolroom/rules.py`

`FineRule` (an ABC), the `RULES` registry, `register` and `get_rule` exist so that fine rules can be plugged in, but SPEC R7 defines exactly one fine and nothing in the repository registers a second rule. Not required by any SPEC line; remove it and compute the fine directly in `fines.py`.

### 4. `--rounding` with four modes - `toolroom/fines.py:4-19`, `toolroom/cli.py:29`

R7 asks for one behaviour: three quarters, rounded to the nearest cent, halves up. The branch adds `nearest`, `up`, `down` and `even` and a `--rounding` option to choose between them. Nobody asked for the other three modes; drop the option and the `rounding` parameter of `round_div`.

### 5. `ToolCache` is unnecessary - `toolroom/cache.py`

Reloading the tools through a time-limited cache (`ttl=300`) in a command that runs once, by hand or from the nightly job (R1), has no use, and the spec never mentions caching. `overdue_loans` can take the `tools` dict that `main` already loaded. Remove `cache.py`.

## Checked and found right

- Overdue days and fines (R6, R7): a loan due today is not overdue, returned loans are skipped, 50 cents a day, the cap comes before the discount, halves round up.
- `--format csv` (R9): the header and the fine format are as specified.
- The notice retry (R11): three attempts, one second apart, no sleep after the last, and the error message is as specified.
