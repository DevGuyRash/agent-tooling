# Review of feature/overdue-notices

## Findings

1. R8 (`toolroom/overdue.py:21`): `reverse=True` on the `(days, member, loan)` key puts equal-day loans in Z-A name order. The spec says A to Z.
2. R10 (`toolroom/notices.py:15`): `total_owed` is `days * 50`, which ignores the cap and the supporter discount and so is not the sum of the listed fines.
3. `ToolCache` has no test for the case where the tools file changes during a run, and its `hits` and `misses` counters are never read; add a test or expose them.
4. `--rounding` is not in the README and has no test through the command line; document it and add a test for `even`.
5. The `register` decorator in `rules.py` does not reject an empty name; validate it, and cover `get_rule` with an unknown name in the CLI tests.
6. `write_notice` could log each failed attempt before it sleeps.
