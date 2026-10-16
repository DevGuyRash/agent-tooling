# Review of feature/overdue-notices

## Findings

### 1. The total on a notice ignores the cap and the supporter discount (R10) - `toolroom/notices.py:15`

R10 says the total is the sum of the fines listed on the notice. `total_owed` multiplies the summed days by 50 cents instead, so a loan capped at the tool's replacement value (R7) or discounted for a supporter is listed at one amount and totalled at another. Use `sum(row.fine for row in rows)`.

### 2. A rule registry for a single rule - `toolroom/rules.py`

`FineRule` (an ABC), `RULES`, `register` and `get_rule` exist so fine rules can be plugged in, but R7 defines exactly one fine and nothing registers a second one. Not required by any SPEC line; remove it.

### 3. `--rounding` with four modes - `toolroom/fines.py`, `toolroom/cli.py:29`

R7 asks for one rounding behaviour. Nobody asked for the other three modes; drop the option.

### 4. `ToolCache` is unnecessary - `toolroom/cache.py`

The command runs once and the spec never mentions caching. Remove `cache.py`.

## Checked

- Ordering (R8): most overdue first, ties by member name and loan id.
- The retry (R11) and `--format csv` (R9) are as specified.
