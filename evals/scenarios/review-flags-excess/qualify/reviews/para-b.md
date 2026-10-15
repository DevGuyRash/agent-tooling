Here's what I found going through the branch against the spec.

## Bugs

- Sorting (R8): the tie-break comes out backwards. `reverse=True` on a `(days, member, loan)` tuple means names are Z-A. The spec says A-Z, then loan id.
- Notice footer (R10): `total_owed` re-derives the amount as days*50 instead of adding up `row.fine`, so it doesn't agree with the lines above it once a cap or a supporter discount kicks in.

## Over-building

I'd cut these. None of them is required by the spec, and each one is YAGNI for a once-a-night script:

- the `FineRule` interface plus registry (one rule exists),
- the four-way `--rounding` switch (R7 wants a single rule),
- the TTL-based `ToolCache`.

## Spec-mandated, so leave alone

The three-try write loop (R11) and `--format csv` (R9) are both in the spec.
