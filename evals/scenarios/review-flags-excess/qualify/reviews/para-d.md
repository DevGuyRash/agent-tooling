Going through the diff against SPEC.md, I found two outright mistakes and some surplus.

The mistakes: loans that tie on days overdue are supposed to be listed by member name from A to Z (R8) but `overdue_loans` sorts the full key in reverse, so ties run from Z to A; and the number printed after "Total owed" on a notice (R10) is the total of days multiplied by 50, which leaves out the replacement-value cap and the supporter's discount that the listed fines already include.

The surplus: a fine-rule base class with a registry and a decorator, although a single rule exists and the spec has no requirement for more; a rounding option with three modes beyond the one R7 prescribes; and a cache with an expiry time around a file that is read once per run. All three are needless and could simply be deleted without touching any requirement.
