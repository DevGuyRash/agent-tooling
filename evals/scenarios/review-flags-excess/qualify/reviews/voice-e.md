# Action items

## Fix (wrong against the spec)
- [ ] R8: equal-day loans are listed Z->A. `reverse=True` in overdue.py:21 flips the name/loan tie-break.
- [ ] R10: notice total != sum of listed fines. notices.py:15 uses days*50.

## Drop (not asked for)
- [ ] `FineRule`/`RULES`/`register`/`get_rule` in rules.py
- [ ] `--rounding` and the `up`, `down`, `even` modes
- [ ] `ToolCache` (cache.py)

## Add
- [ ] a test with two loans on the same day count
- [ ] a test for a capped / supporter notice

## Leave as is
- [x] write retry (R11)
- [x] --format csv (R9)
