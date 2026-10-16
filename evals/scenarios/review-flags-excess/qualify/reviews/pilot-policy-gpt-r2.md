# Review: feature/overdue-notices

Compared with `main`, against SPEC.md R6–R11. Five findings: three correctness/spec issues and two instances of over-engineering.

## Findings

1. **[P1] Notice totals ignore discounts and replacement-value caps.** `toolroom/notices.py:13–15` computes total overdue days times 50 instead of summing `row.fine`, contrary to R10. A supporter with two one-day loans sees two fines of `0.38` but a total of `1.00` instead of `0.76`. A standard member with a ten-day loan on a tool worth 100 cents sees a fine of `1.00` and a total of `5.00`. Sum the already calculated fines. The existing notice tests only use uncapped standard fines, so they miss both cases.

2. **[P2] Equal-day loans have both tie-breakers reversed.** `toolroom/overdue.py:21` applies `reverse=True` to the entire `(days, member, loan)` key. R8 requires descending days but ascending member names and loan ids. With equally overdue loans `L-1` and `L-2` for Alice and `L-3` for Zoe, the implementation returns `L-3, L-2, L-1`; the required order is `L-1, L-2, L-3`. This affects text, CSV, and equal-day ordering within notices under R10. Sort by `(-row.days, row.member, row.loan)` and cover both tie-breakers; current ordering tests use distinct due dates only.

3. **[P2] The added rounding option allows fines that violate R7.** `toolroom/cli.py:29,43` exposes and forwards `--rounding`, while `toolroom/fines.py:7–19,22–26` implements selectable policies. R7 fixes nearest-cent rounding with halves up; it gives the operator no choice of policy. For a supporter three days overdue on an uncapped loan, `overdue --rounding even` prints `1.12` rather than the required `1.13`; `down` also undercharges, and `up` can overcharge a capped fine with a fractional cent below one half. Remove the option and alternate policies and always apply R7. The rounding-mode test currently endorses these noncompliant results.

4. **[P3] The TTL tool cache adds machinery to an already loaded dictionary.** `toolroom/cache.py:5–25`, used by `toolroom/overdue.py:10–19` and `toolroom/cli.py:43`, introduces an injected loader and clock, expiry state, and hit/miss counters. The CLI has already loaded and validated the complete tools dictionary at line 33, and R1 limits each manual/nightly run to 200 tools and 500 loans. The first cache lookup unnecessarily reads the same CSV again; none of R6–R11 calls for refreshing tools during a run. Pass the validated dictionary into `overdue_loans` and use direct lookups, removing the cache and its TTL-only test.

5. **[P3] A rule registry and class hierarchy are unnecessary for the single fixed fine rule.** `toolroom/rules.py:4–42` adds a global registry, registration decorator, abstract base class, duplicate/unknown-name handling, and instance construction. Its only production caller, `toolroom/fines.py:24`, always requests the literal `"per-day"`; R7 fixes that rule at 50 cents per day. These extension points and their registry tests add maintenance work without implementing a required feature. Calculate `days * 50` directly before applying the cap and supporter discount.

## Validation

- `make check`: all 33 tests pass.
- Focused, temporary checks reproduced findings 1–3, including the CLI rounding result.
- A separate two-member CLI check confirmed R11's permanent-failure behavior: three write attempts, two one-second sleep calls, the required stderr message, exit status 0, and successful creation of the next member's notice. The committed tests do not exercise that complete continuation scenario.
- R6 filtering and day calculation, default R7 fine calculation, and R9 text/CSV formatting otherwise match the requirements inspected. No code or tests were changed.
