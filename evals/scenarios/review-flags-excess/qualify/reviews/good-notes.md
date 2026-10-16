Review notes - feature/overdue-notices

- [ ] R8: ties come out in reverse. `reverse=True` flips the name and loan-id tie-break, expected A-Z. (overdue.py)
- [ ] R10: total_owed = days * 50 - not the sum of the fines (cap / supporter discount lost). (notices.py)
- [ ] rules.py: ABC + registry with a single implementation. Speculative generality, YAGNI. Inline it.
- [ ] --rounding (4 modes): R7 only wants half-up. Over-built; hard-code half-up.
- [ ] ToolCache: caching a file the CLI reads once. Not in the spec; can go.
- [x] retry on notice write: R11, keep
- [x] --format text|csv: R9, keep
