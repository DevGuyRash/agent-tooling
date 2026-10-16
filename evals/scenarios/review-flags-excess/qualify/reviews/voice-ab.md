## Reviewer 2

The reviewer found that the tie-break in `overdue_loans` is inverted by `reverse=True`: member name and loan id run Z-A where R8 prescribes A-Z. The reviewer also found that `total_owed` multiplies days by fifty cents, so a notice's total contradicts its own fine lines whenever a cap or a supporter discount applies (R10).

The reviewer recommends collapsing `rules.py` into a plain function (one rule, no requirement for more), hard-coding the half-up rounding of R7 in place of the `--rounding` modes, and deleting `cache.py` (a TTL cache in a command that runs once).

The reviewer checked the retry in `write_notice` and the CSV format against R11 and R9 and has no comment on either.
