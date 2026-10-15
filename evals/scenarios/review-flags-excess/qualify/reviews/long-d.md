# Review

## Spec conformance

| Requirement | Status | Notes |
|---|---|---|
| R6 overdue definition | OK | due today is not overdue, returned never overdue |
| R7 fine | OK | 50c/day, cap, supporter 3/4, halves up |
| R8 ordering | **FAIL** | `reverse=True` on the whole key lists equal-day loans Z-A (`overdue.py:21`) |
| R9 output | OK | text and CSV |
| R10 notices | **FAIL** | total uses `days * 50`, so it ignores the cap and the discount (`notices.py:15`) |
| R11 retry | OK | 3 attempts, 1 s apart |

## Code outside the spec

These are not tied to any requirement:

| What | Where | Why it matters |
|---|---|---|
| `FineRule` ABC + registry | `rules.py` | One implementation; adds a module and 40 lines for no requirement |
| Rounding modes / `--rounding` | `fines.py`, `cli.py` | R7 has a single rounding rule |
| `ToolCache` | `cache.py` | Caches a file that is read once per run |

Recommendation: remove all three; they are unrelated to R6-R11.

## Test gaps

No tests for equal-day ordering, for a capped notice, or for a supporter's notice.
