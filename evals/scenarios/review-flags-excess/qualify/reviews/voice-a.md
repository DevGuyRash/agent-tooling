# Findings

1. High - `toolroom/overdue.py:21`
   `rows.sort(..., reverse=True)` is applied to the tuple `(row.days, row.member, row.loan)`. This sorts the days from largest to smallest, as required, but it also sorts member names and loan IDs from Z to A. SPEC R8 requires ascending order for those two keys. As a result, equal-day loans are not listed in the required order.
   Recommendation: use `key=lambda row: (-row.days, row.member, row.loan)` and remove `reverse=True`.

2. High - `toolroom/notices.py:13-15`
   `total_owed` multiplies the sum of overdue days by `CENTS_PER_DAY`. SPEC R10 requires the total to be the sum of the fines listed in the notice. Those fines come from `fine_for`, which applies the replacement-value cap and the supporter discount. The notice can therefore show a total that differs from its own line items.
   Recommendation: sum `row.fine`.

3. Medium - `toolroom/rules.py`
   The fine calculation is placed behind an abstract `FineRule`, a global `RULES` registry, a `register` decorator and `get_rule`. There is only one implementation and the SPEC does not describe alternative fine rules, so the abstraction is not needed by the requirements and increases the amount of code to maintain.
   Recommendation: replace it with a direct function.

4. Medium - `toolroom/fines.py`, `toolroom/cli.py`
   The `--rounding` option supports four rounding modes. SPEC R7 defines a single rounding behaviour (nearest cent, halves up). The additional modes are outside the specified behaviour.
   Recommendation: remove the option and its parameter threading.

5. Low - `toolroom/cache.py`
   `ToolCache` introduces a time-based cache for data that is loaded once for each invocation. The SPEC does not require caching, so this adds state and complexity without supporting a requirement.
   Recommendation: remove it.

No issue found with the retry behaviour in `write_notice` (R11) or the `--format` option (R9); both follow the SPEC.
