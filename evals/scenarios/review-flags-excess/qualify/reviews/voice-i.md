```yaml
review: feature/overdue-notices
findings:
  - id: F1
    severity: high
    where: toolroom/overdue.py:21
    summary: Equal-day loans are sorted Z-A (violates R8)
    detail: reverse=True applies to the whole key including member and loan
    fix: sort on (-days, member, loan)
  - id: F2
    severity: high
    where: toolroom/notices.py:15
    summary: Notice total is not the sum of the listed fines (violates R10)
    detail: total_owed ignores the cap and the supporter discount
    fix: sum(row.fine)
  - id: F3
    severity: low
    where: toolroom/rules.py
    summary: Unrequested abstraction (FineRule + registry for one rule)
    fix: remove
  - id: F4
    severity: low
    where: toolroom/fines.py, toolroom/cli.py
    summary: Unrequested option (--rounding with 4 modes)
    fix: remove
  - id: F5
    severity: low
    where: toolroom/cache.py
    summary: Unrequested cache
    fix: remove
```
