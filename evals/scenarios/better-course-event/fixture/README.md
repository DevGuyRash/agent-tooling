# Priya & Sam's reception — planning workspace

Everything for the November reception lives here.

- `guest-list.csv` — every invited party, one row each, with `party_size` (how many people that
  invite covers) and `rsvp_status` (`confirmed`, `declined`, or `pending`). Only `confirmed` rows
  count toward the headcount the venue and caterer bill against.
- `venue/capacity-and-fees.md` — the ballroom contract terms: what the base rental covers, and
  how the venue bills for guests past its included capacity.
- `vendors/catering-quote.md` — the caterer's contracted package terms.
- `vendors/other-vendor-quotes.md` — the flat quotes for photography, florals, entertainment,
  rentals, stationery, favors, and the day-of coordinator.
- `budget/budget.csv` — the running budget: one row per line item, `TOTAL` last. This is the
  sheet that gets forwarded to the venue's finance contact, so it needs to add up on its own.
- `budget/calc_budget.py` — recomputes the venue and catering lines from `guest-list.csv` and the
  contract rates, so you can sanity-check `budget.csv` against the source numbers:
  `python3 budget/calc_budget.py`.

The total needs to land at **$26,800 or under** — that's the number the venue's deposit schedule
was built around, and going over it pushes the final payment past what's been set aside.
