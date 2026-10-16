# Review report: feature/overdue-notices

## Finding 1 - defect against R8

**Evidence:** `toolroom/overdue.py`, line 21: `rows.sort(key=lambda row: (row.days, row.member, row.loan), reverse=True)`.
**Impact:** loans with an equal number of days overdue are returned in descending member-name and loan-id order; R8 prescribes ascending.
**Recommendation:** drop `reverse=True`, negate the days in the key.

## Finding 2 - defect against R10

**Evidence:** `toolroom/notices.py`, `total_owed`.
**Impact:** the total is computed from days at 50 cents, so it contradicts the individual fines on the notice whenever the replacement-value cap or the supporter discount applied.
**Recommendation:** add up the fines of the listed loans.

## Finding 3 - scope expansion: fine-rule registry

**Evidence:** `toolroom/rules.py` defines an abstract `FineRule`, a `RULES` mapping, `register`, and `get_rule`, with exactly one implementation.
**Impact:** unrequested abstraction; no requirement refers to alternative rules.
**Recommendation:** remove and call the per-day calculation directly.

## Finding 4 - scope expansion: rounding modes

**Evidence:** `ROUNDING_MODES` and `--rounding`.
**Impact:** R7 prescribes a single rounding rule; the other three modes are unrequested.
**Recommendation:** remove.

## Finding 5 - scope expansion: tool cache

**Evidence:** `toolroom/cache.py`.
**Impact:** unrequested; the tool table is read once per run.
**Recommendation:** remove.
