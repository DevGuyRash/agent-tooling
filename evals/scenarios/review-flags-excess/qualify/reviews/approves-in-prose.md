The branch implements R6 to R11 and its 33 tests pass. The ordering in overdue_loans follows R8 (most days first, ties by name and then loan id), and the total in the notice follows R10. The fine and the supporter discount in fines.py match R7.

What I would change: rules.py defines an abstract FineRule with a registry although there is only one fine rule, which is more machinery than the spec needs; the --rounding option with four modes is unrequested because R7 fixes the rounding; and ToolCache is not needed in a program that runs once. All three can be removed.
