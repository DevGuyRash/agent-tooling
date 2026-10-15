# Review of feature/overdue-notices

Three things in the branch go beyond the spec.

1. `toolroom/rules.py` is an abstract `FineRule` with a `RULES` registry and a single implementation. Nothing requires it. Remove it.
2. `--rounding` and its four modes: R7 fixes nearest, halves up. Unrequested; drop it.
3. `ToolCache`: the spec never mentions caching and the command runs once. Delete it.

## Verified against the spec

- R8 ordering: `overdue_loans` sorts by days with `reverse=True`, so the most overdue loans come first, ties by member name and loan id as required. Matches.
- R10 notice total: `total_owed` gives the total owed for the member, as the spec says. Matches.
- R11 retry and R9 `--format csv`: as specified.
