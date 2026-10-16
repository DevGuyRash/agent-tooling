# Review

I am a bit worried about how many moving parts the fine calculation has. There is an abstract base class, a registry, a decorator, a lookup function, four rounding modes selected from the command line, and a cache with an expiry time, and R6 to R8 describe a flat fifty cents a day with a cap, a three-quarters discount for supporters and one rounding rule. None of the extra parts is needed for that, so I would reduce it to a single function.

More urgent: two requirements are not met.

- R8: with `reverse=True` on the combined key, the tie-break on member name and loan id is reversed.
- R10: `total_owed` returns days times fifty, so the total of a notice leaves out the cap and the discount that its lines include.

The retry loop and the CSV output are in the spec (R11, R9).
