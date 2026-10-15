Review comment(s):

- [P1] Keep equal-day tie-breaks ascending — toolroom/overdue.py:21-21
  `rows.sort(..., reverse=True)` reverses the whole `(days, member, loan)` key. R8 only wants days descending; for equal days the member name should be A-Z and then the loan id, but this sorts both Z-A.

- [P1] Use the displayed fines for the notice total — toolroom/notices.py:13-15
  `total_owed` is `sum(row.days) * CENTS_PER_DAY`, while each line prints `row.fine`. Once a loan is capped by the tool value or discounted for a supporter, the printed total no longer equals the sum of the lines, contrary to R10.

- [P3] Remove the unrequested fine-rule registry — toolroom/rules.py:1-42
  SPEC R7 defines one fine. An ABC, a global registry and a lookup function add indirection that no requirement uses.

- [P3] Drop the unrequested rounding modes — toolroom/fines.py:4-19
  R7 specifies nearest-cent, halves up. `up`, `down` and `even` (and the `--rounding` option) are not required.

- [P3] Drop the tool cache — toolroom/cache.py:1-25
  The process loads the tool table and exits, so a TTL cache is unnecessary and the SPEC does not mention one.
