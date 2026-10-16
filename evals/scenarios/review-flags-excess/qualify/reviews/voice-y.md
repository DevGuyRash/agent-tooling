BUG - TIES: loans with same days are sorted in reverse for name and id, reverse=True in overdue_loans. R8 = ascending.
BUG - TOTAL: notice total is DAYS * 50, NOT the sum of the fines. cap and supporter discount are ignored. R10.
NOT NEEDED: FineRule abstract class and RULES registry (only one rule).
NOT NEEDED: --rounding with 4 modes (R7 = 1 mode).
NOT NEEDED: ToolCache, program runs once.
OK: retry (R11), csv (R9).
