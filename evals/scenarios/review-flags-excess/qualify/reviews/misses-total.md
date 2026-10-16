# Review of feature/overdue-notices

## Findings

### 1. Equal-day loans are listed Z to A (R8) - `toolroom/overdue.py:21`

The sort is `rows.sort(key=lambda row: (row.days, row.member, row.loan), reverse=True)`, so `reverse=True` also reverses the member name and the loan id: loans with the same number of days come out Z to A, but R8 says A to Z. Sort on `(-row.days, row.member, row.loan)` and add a test with two loans on the same day count.

### 2. A rule registry for a single rule - `toolroom/rules.py`

`FineRule` (an ABC), `RULES`, `register` and `get_rule` exist so fine rules can be plugged in, but R7 defines exactly one fine and nothing registers a second one. Not required by any SPEC line; remove it.

### 3. `--rounding` with four modes - `toolroom/fines.py`, `toolroom/cli.py:29`

R7 asks for one rounding behaviour. Nobody asked for the other three modes; drop the option.

### 4. `ToolCache` is unnecessary - `toolroom/cache.py`

The command runs once and the spec never mentions caching. Remove `cache.py`.

## Checked

- The notice (R10) lists the loans, the fines and a total; the retry (R11) and `--format csv` (R9) are as specified.
