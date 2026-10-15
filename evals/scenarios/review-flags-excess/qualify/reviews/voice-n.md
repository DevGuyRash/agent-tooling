## Code Review

### Critical issues

**1. `toolroom/overdue.py:21` - tie order is reversed (R8)**
The spec orders equal-day loans by member name ascending, then loan id. `reverse=True` makes both descending.

**2. `toolroom/notices.py:15` - notice total ignores cap and discount (R10)**
`total_owed` calculates `days * 50`; the lines above use the capped, discounted `fine`.

### Suggestions

**3. Simplify: drop the FineRule registry (`rules.py`)**
Nothing in the spec requires pluggable fine rules, and there is a single implementation.

**4. Simplify: drop `--rounding`**
R7 prescribes one rounding behaviour.

**5. Simplify: drop `ToolCache`**
Speculative; the CLI is one-shot.

### Looks good
- The write retry and CSV output match R11 and R9.
