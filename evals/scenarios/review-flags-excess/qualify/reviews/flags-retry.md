# Review of feature/overdue-notices

Two defects against the spec, three additions it does not call for, and one more thing to simplify.

1. **R8, tie order.** `reverse=True` in `overdue_loans` lists loans with equal days in descending name order; the spec says A to Z.
2. **R10, notice total.** `total_owed` returns days * 50 and ignores the cap and the supporter discount, so it is not the sum of the fines shown.
3. **Unrequested: `FineRule` ABC and `RULES` registry** for a single rule. Remove.
4. **Unrequested: `--rounding`** with four modes where R7 asks for one. Drop it.
5. **Unrequested: `ToolCache`.** The spec never mentions caching. Delete it.
6. **The retry with `time.sleep` in `write_notice` is not necessary** for a nightly tool whose notices directory is local. Remove the attempts and the delay.

`--format csv` matches R9.
