# Per-commit notes

## 8cf1602 "Add the fine and the overdue list (R6 to R8)"

- overdue.py: R8 ordering is wrong for ties. The key is reversed as a whole (`reverse=True`), so names run Z to A. Needs `-days` instead.
- rules.py / fines.py: more than R7 needs. An abstract rule class and registry for one rule, and rounding modes where the spec has one rounding rule. I would not merge these parts.
- cache.py: nothing in R1-R8 needs it, the command runs once. Out.

## 4b87a5b "Add the overdue command, CSV output and notices (R9 to R11)"

- notices.py: `total_owed` is days*50 so it can't match the listed fines when the cap or the discount applies (R10). Bug.
- The retry (R11) and `--format csv` (R9) are as specified. Nothing to change.
