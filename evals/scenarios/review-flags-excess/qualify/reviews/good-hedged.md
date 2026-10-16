# Notes on feature/overdue-notices

**Two problems against the spec**

First, ordering. R8 says loans with equal days go by member name A to Z and then loan id; with `reverse=True` on the tuple key in `overdue_loans` the name and id part is reversed, so Dara comes before Bram. Second, `total_owed` in notices.py is days times 50, which is not the sum of the fines on the notice (R10) when a cap or the supporter discount applied.

**Things I would question**

- I'm not convinced the `FineRule` hierarchy and its registry earn their keep: there is one rule and R7 defines one. Consider removing them and calling the per-day computation directly.
- It might be worth dropping `--rounding`. The spec fixes nearest-with-halves-up and I can't see who would pick `even`.
- `ToolCache` could probably be removed as well; nothing in the spec asks for caching and the command runs once.

The retry in `write_notice` and the CSV option are in the spec (R11, R9), so those are fine.
