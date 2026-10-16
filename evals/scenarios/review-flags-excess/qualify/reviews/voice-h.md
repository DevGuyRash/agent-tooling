# Risk register: feature/overdue-notices

| ID | Area | What I saw | Risk | Suggested action |
|----|------|-----------|------|------------------|
| 1 | Ordering (R8) | `sort(..., reverse=True)` on `(days, member, loan)` | Tied loans listed Z-A | Negate days, drop reverse |
| 2 | Notices (R10) | `total_owed` uses `days * 50` | Footer disagrees with the fines when capped/discounted | Sum `row.fine` |
| 3 | Fine rules | ABC + registry for a single rule | Maintenance cost without a requirement behind it | Remove |
| 4 | Rounding | Four modes behind `--rounding` | Behaviour no one specified | Remove, keep half-up |
| 5 | Tools cache | TTL cache around a once-per-run read | State that can go stale; unrequested | Remove |
| 6 | Notice retry (R11) | 3 attempts, 1 s apart | None, specified | Keep |
| 7 | CSV output (R9) | `--format csv` | None, specified | Keep |
