# Review: feature/overdue-notices

## What I found

1. **Tie order is wrong (R8).** `overdue_loans` sorts `(days, member, loan)` with `reverse=True`. The reverse flag applies to the whole tuple, so the names and loan ids of loans with equal days come out in descending order. The spec says A to Z.
2. **The notice total is wrong (R10).** `total_owed` returns the number of days times 50 cents. R10 wants the sum of the listed fines, which already include the cap and the supporter discount, so the two disagree whenever either applies.
3. **`FineRule` and its registry are not needed.** There is a single implementation and no requirement for a second; SPEC R7 describes one fine. The abstract class, `RULES`, `register` and `get_rule` can be removed.
4. **`--rounding` is not needed.** R7 gives one rounding rule. The `nearest`, `up`, `down` and `even` modes are unrequested.
5. **`ToolCache` is not needed.** The program runs once and the spec never mentions caching; the cache and its TTL can be deleted.

## Things that look like extras but are required

At first glance the retry loop in `write_notice` and the `--format` option look like over-engineering for a small tool. They are not: R11 requires three attempts one second apart, and R9 requires the CSV output with that header. I left both alone.
