review of feature/overdue-notices vs SPEC.md

bugs
- overdue.py:21 reverse=True also reverses name + loan id. R8 says A-Z / ascending for ties. 
- notices.py:15 total = days*50, ignores cap + supporter 3/4. R10 says sum of fines.

cruft
- rules.py ABC + registry, 1 impl. no R# asks for it. kill
- --rounding, 4 modes. R7 = 1 mode. kill
- ToolCache TTL. cli runs once. kill

fine
- retry R11
- csv R9
