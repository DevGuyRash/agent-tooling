# Review of feature/overdue-notices

Read against SPEC.md R6 to R11. Two requirements are not met and the change adds several things the spec does not ask for.

## Findings

### 1. Equal-day loans are listed Z to A (R8) - `toolroom/overdue.py:21`

`rows.sort(key=lambda row: (row.days, row.member, row.loan), reverse=True)` reverses the member name and the loan id as well as the days, so loans with the same number of days are ordered Z to A. R8 says A to Z. Sort on `(-row.days, row.member, row.loan)`.

### 2. The total on a notice ignores the cap and the discount (R10) - `toolroom/notices.py:15`

`total_owed` multiplies the days by 50 instead of summing the fines on the notice, so it is wrong for a capped loan or a supporter. Use `sum(row.fine for row in rows)`.

### 3. Abstract `FineRule` and a registry for one rule - `toolroom/rules.py`

Over-engineering: one implementation, nothing registers another, and R7 defines a single fine. Remove it.

### 4. `--rounding` and its four modes - `toolroom/cli.py:29`

Not asked for: R7 fixes the rounding as nearest, halves up. Drop the option.

### 5. `ToolCache` - `toolroom/cache.py`

The spec never mentions caching and the command runs once. Unnecessary; delete it.

### 6. The retry loop in `write_notice` is unnecessary - `toolroom/notices.py:25-35`

Sleeping and trying a file write three times is over-engineering for a command line tool, and the spec does not ask for it. Remove `ATTEMPTS` and `DELAY` and write the file once.

### 7. The `--format` option and the CSV renderer were not requested - `toolroom/render.py`, `toolroom/cli.py:27`

Nothing in the spec asks for a second output format. Drop `render_csv` and the option and keep the text list.
