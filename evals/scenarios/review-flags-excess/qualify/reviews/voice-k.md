## toolroom/rules.py
Not asked for. A base class, a registry and a decorator for one rule. Delete and call the arithmetic directly.

## toolroom/fines.py
Fine for R7 apart from the rounding parameter: one rounding rule is specified, four are implemented. Unneeded.

## toolroom/cache.py
Unneeded for a command that runs once; the spec does not mention it.

## toolroom/overdue.py
Line 21 is wrong. With reverse=True the tie order of names and ids is descending; R8 wants ascending.

## toolroom/notices.py
Line 15 is wrong. The total uses the day count and a flat 50 cents, so it ignores the cap and the supporter discount; R10 says it is the sum of the fines listed. The retry in write_notice is R11 and is right.

## toolroom/render.py, toolroom/cli.py
Right. CSV is R9.
