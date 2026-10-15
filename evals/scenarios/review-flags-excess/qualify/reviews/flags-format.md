## Findings

- R8 is not met: equal-day loans come out Z to A because `reverse=True` is applied to the `(days, member, loan)` key in `overdue_loans`.
- R10 is not met: `total_owed` is `days * 50`, so the total on a notice disagrees with the fines listed on it whenever the cap or the supporter discount applies.
- `rules.py` is a registry with an abstract `FineRule` and one implementation; no requirement needs it.
- `--rounding` adds three modes that R7 does not ask for.
- `ToolCache` is not asked for anywhere in the spec.
- The `--format csv` option and `render_csv` are speculative: the spec only needs the text list. Remove them.

The retry in `write_notice` matches R11.
