**Review - `feature/overdue-notices`**

1. **[major] Wrong tie-break (R8).** Loans that share a days-overdue figure should list member names A to Z and then by loan id. `overdue_loans` passes the whole `(days, member, loan)` tuple to `sort(..., reverse=True)`, so everything, including the name order, is descending. Nothing in the tests has a tie.
2. **[major] Notice total (R10).** `total_owed()` is `sum(days) * CENTS_PER_DAY` while each line shows `row.fine`. For capped or supporter loans the footer won't equal the sum of the lines.
3. **[minor] No SPEC item asks for a plug-in layer.** `rules.py` introduces `FineRule`, a `RULES` table and `@register`, yet only `PerDayRule` exists. Could be dropped in favour of a plain function.
4. **[minor] Four rounding strategies.** R7 specifies one (nearest, halves up). `ROUNDING_MODES` / `--rounding` are surplus.
5. **[minor] `ToolCache`.** A TTL cache for a process that lives for a few milliseconds. Not something the spec needs.
