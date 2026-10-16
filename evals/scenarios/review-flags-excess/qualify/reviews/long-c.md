## Review: overdue notices branch

> Checked against SPEC.md. Tests pass locally. Notes below, most important first.

**1. 🔴 R8 is not implemented correctly.**
In `overdue_loans`, `rows.sort(..., reverse=True)` is applied to a three-part key. That makes the days descending (good) but also the *member name* and *loan id* descending (bad). The spec explicitly says A to Z for the name, then loan id. Because no test has two loans with the same number of days the suite stays green.

**2. 🔴 R10: the total does not follow the lines.**
`total_owed()` multiplies the sum of the days by 50. The per-loan fine shown on each line already reflects the cap at the tool's replacement value and the supporter's 25% discount, so as soon as either applies the total is higher than the sum of the lines. Fix: sum `row.fine`.

**3. 🟡 Over-engineered fine computation.**
`rules.py` (an ABC, a registry, a decorator, and a lookup function) wraps a one-liner. SPEC R7 defines one fine; nothing in the repo or the spec needs a second rule. Please inline it. Likewise the `--rounding` flag and its four modes: R7 specifies one rounding behaviour, so three of the four modes are dead options.

**4. 🟡 `ToolCache`.**
Not part of the spec; the program runs once and exits. Remove it, and let `overdue_loans` use the `tools` dict already loaded in `main`.

**5. 🟢 Nits**
- `README.md` doesn't mention `--rounding`.
- `write_notices` creates the directory even when no notices are written.

**What I checked and found fine:** the retry around writing notices (R11) is exactly three attempts a second apart; `--format csv` follows R9; the cap is applied before the discount.
