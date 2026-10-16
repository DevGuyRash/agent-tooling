## Does not meet the spec

- **Tie order (R8)** - `overdue_loans` ends with `rows.sort(..., reverse=True)`. With a `(days, member, loan)` key that reverses the names and ids as well, so loans with the same days are listed Z to A. R8 says A to Z.
- **Notice total (R10)** - `total_owed` is `sum(days) * 50`. It is not the sum of the fines on the notice whenever the cap or the supporter discount applied.

## Nobody asked for these

- `FineRule` ABC, `RULES`, `register`, `get_rule` (rules.py): one rule, one implementation.
- `--rounding` and its four modes (fines.py, cli.py).
- `ToolCache` with a TTL (cache.py).

## Fine as they are

- The write retry (R11) and `--format csv` (R9) do what the spec says.
