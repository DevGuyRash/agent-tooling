# Review

Overall the branch does what R6-R11 ask, with these exceptions.

## Does not match the spec

### Ties in the overdue list
Where: `overdue_loans`.
Expected (R8): same days -> member name A-Z -> loan id.
Actual: `reverse=True` on the whole key, so Z-A for names and ids.

### Total on a notice
Where: `total_owed`.
Expected (R10): the sum of the fines listed.
Actual: days * 50, so no cap and no supporter discount.

## Goes beyond the spec

### Fine rule registry
Where: `rules.py`.
Why it is extra: one implementation, no requirement.
Do: remove.

### Rounding modes
Where: `fines.py`, `cli.py`.
Why it is extra: R7 has one rounding rule.
Do: remove.

### Tool cache
Where: `cache.py`.
Why it is extra: the program runs once.
Do: remove.
