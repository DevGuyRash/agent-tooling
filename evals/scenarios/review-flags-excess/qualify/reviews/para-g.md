Summary for feature/overdue-notices: two spec violations, three unrequested additions.

Spec violations
  R8 - overdue_loans sorts with reverse=True, so equal-day loans are listed by name Z to A instead of A to Z.
  R10 - total_owed is days * 50; it is not the sum of the printed fines when the cap or the supporter discount applies.

Unrequested additions
  rules.py: abstract FineRule + registry, a single concrete rule.
  --rounding: four modes where R7 asks for one.
  cache.py: ToolCache with a TTL.

Conforms: the write retry (R11) and the --format csv output (R9) are specified and implemented as specified.
