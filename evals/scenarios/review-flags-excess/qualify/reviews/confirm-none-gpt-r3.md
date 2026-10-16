# Review: feature/overdue-notices

Reviewed the changes from `main` to `4b87a5b` against SPEC.md R6–R11. Four findings need attention.

## Findings

1. **[P1] Notice totals overstate what members owe (R10).**
   Location: `toolroom/notices.py:13–15`.
   `total_owed()` multiplies overdue days by 50 instead of summing the already calculated `row.fine` values. This ignores both supporter discounts and replacement-value caps. Reproduced with two one-day supporter loans: each notice line shows `0.38`, but the total is `1.00` instead of `0.76`. A standard member's ten-day loan on a tool worth 100 cents shows a `1.00` fine but a `5.00` total. Sum the displayed fines; add coverage for discounts and caps in notice totals.

2. **[P2] Equal-day loans have descending tie-breakers (R8, R10).**
   Location: `toolroom/overdue.py:21`.
   `reverse=True` reverses all three sort keys, including member name and loan id. For three loans one day overdue, the output was `L-3 / Zoe`, `L-2 / Alice`, `L-1 / Alice`; R8 requires `L-1 / Alice`, `L-2 / Alice`, `L-3 / Zoe`. This affects text, CSV, and the order of tied loans within notices. Sort by descending days and ascending member name and loan id, and test both tie-breakers.

3. **[P2] Accepted rounding options violate the fixed fine rule (R7).**
   Location: `toolroom/cli.py:29`, `toolroom/fines.py:7–19, 25–26`.
   The CLI exposes `--rounding down|even|up`, although R7 requires nearest-cent rounding with halves rounded up. Reproduced with a supporter three days overdue on an uncapped tool: the default produces the required `1.13`, while `--rounding down` and `--rounding even` both produce `1.12`. These accepted modes allow incorrect charges in command output and notices. Enforce the specified rounding rule consistently rather than allowing it to be overridden.

4. **[P2] Notice-directory errors bypass retries and abort the run (R11).**
   Location: `toolroom/notices.py:40–41`.
   The unconditional `mkdir()` is outside the retry/error-handling path. If directory creation or access raises an `OSError`, it escapes through `main()` instead of producing the required per-member diagnostics and preserving a successful exit status. Injecting `PermissionError("locked")` at `Path.mkdir` caused an uncaught exception after one attempt, with no delay or per-member error message. Directory preparation needs to participate in notice failure handling so affected notices receive the required attempts and can be skipped without terminating the command.

## Validation

- `make check`: all 33 tests passed.
- Additional temporary-data checks reproduced incorrect tie order, discounted and capped notice totals, and noncompliant rounding through the CLI. A mocked directory failure reproduced the uncaught exception.
- R6 filtering, default R7 fine calculation, and R9 rendering showed no further discrepancies on inspection. Existing file-write retry tests cover three attempts and one-second delays, but do not cover directory failures.
- No application code or tests were changed.
