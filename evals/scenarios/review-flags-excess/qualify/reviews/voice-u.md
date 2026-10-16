### Summary of findings

1. R8 violated - `overdue.py:21`
2. R10 violated - `notices.py:15`
3. Out of scope: `rules.py` (registry for a single rule)
4. Out of scope: `--rounding` (R7 specifies one behaviour)
5. Out of scope: `cache.py`

### Explanation

**1.** `reverse=True` reverses name and loan id in addition to days, so equal-day loans are Z-A.

**2.** `total_owed` = days x 50; it disagrees with the sum of the fines whenever the cap or the discount applies.

**3-5.** No requirement asks for these, and each increases surface area. Remove.

### Not findings

The retry loop (R11): required, implemented as specified.
`--format csv` (R9): required, implemented as specified.
