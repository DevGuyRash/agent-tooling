# Review of feature/overdue-notices

## Findings

1. `toolroom/overdue.py:21` - R8: `reverse=True` on the `(days, member, loan)` key lists equal-day loans in descending name order. Spec says A to Z.
2. `toolroom/notices.py:15` - R10: `total_owed` is days x 50 and ignores the cap and the supporter discount, so it is not the sum of the listed fines.
3. `toolroom/rules.py` - the abstract `FineRule` and the `RULES` registry serve one rule. Unrequested; remove them.
4. Tests: nothing covers equal-day loans or a capped or discounted notice.
5. `--rounding` and `ToolCache` could use a line each in the README.
