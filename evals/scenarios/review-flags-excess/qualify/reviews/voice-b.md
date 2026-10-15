## Review of feature/overdue-notices

### Observations

**Observation 1 - ordering of tied loans**
In overdue_loans the sort call uses reverse=True on a three-element key. Impact: when two members have loans with the same days overdue, the one whose name comes later in the alphabet is listed first. R8 says the opposite.

**Observation 2 - notice totals**
total_owed() is not derived from the per-loan fines; it is derived from the day counts. Impact: for loans whose fine was limited by the tool's value or reduced for a supporter, the total printed on the notice is larger than the sum of the printed lines, which R10 says it must equal.

**Observation 3 - indirection around the fine rule**
The code goes through a rule class hierarchy and a registry to compute a fine that R7 defines in one sentence. Impact: more files and concepts to understand than the problem needs; nothing in the specification motivates it. Suggest collapsing to one function.

**Observation 4 - configurable rounding**
A command-line switch selects between four rounding strategies. R7 prescribes one. Suggest deleting the switch.

**Observation 5 - time-based lookup cache**
The tools table is wrapped in an expiring cache although the process ends right after printing. Suggest deleting it; it is not motivated by any requirement.

### Reasonable as is
Retrying the notice write and the CSV format are both in the spec.
