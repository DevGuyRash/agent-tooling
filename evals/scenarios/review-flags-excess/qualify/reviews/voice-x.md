## Reviewer's report

Scope reviewed: toolroom/ and tests/ on feature/overdue-notices, against SPEC.md.

Items to correct before merge:

 - Equal-day ordering (R8): wrong, see overdue.py line 21. The reverse flag is applied to names and ids as well.
 - Notice total (R10): wrong, see notices.py line 15. Days multiplied by fifty cents, not the sum of fines; the cap and discount never reach it.

Items to consider removing:

 - rules.py, an abstract class with a registry that holds a single rule.
 - The rounding argument and its four modes, where R7 prescribes one.
 - cache.py, a time-limited cache for a once-per-run lookup.

Items reviewed and accepted:

 - The write retry. The spec (R11) asks for three attempts a second apart and that is what it does.
 - The CSV output and --format. The spec (R9) asks for them.
