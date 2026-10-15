# Notes

**A. Spec deviations**

- A1 (R8): tie order Z-A because of `reverse=True`.
- A2 (R10): footer total ignores cap/discount (`days * 50`).

**B. Unrequested (remove)**

- B1: `FineRule`/registry/`register`/`get_rule`
- B2: `--rounding` modes
- B3: `ToolCache`

**C. Requested (keep)**

- C1: retry on notice write (R11)
- C2: `--format csv` and `render_csv` (R9)

**D. Tests to add**

- D1: equal-day ordering
- D2: capped notice total
