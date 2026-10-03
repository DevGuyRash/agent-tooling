# loanbook due

Asked for by the Saturday volunteers: loans coming due soon, so they can ring people the day before their things are due back. It works like `overdue`, looking forward instead of back.

```
python3 -m loanbook [--data DIR] due [--on DATE] [--within DAYS]
```

`--on` is the first day (default today). `--within` is how many days after it to include, 1 to 14 (default 2), so the default covers today and the next two days. A loan is listed when it has no returned date and its due date is from `--on` to `--on` plus `--within` days, both ends included. Overdue loans are not listed; `overdue` covers those.

```
$ python3 -m loanbook due --on 2026-10-05
Due 2026-10-05 to 2026-10-07

Priya Shah (07700 900314)
  2026-10-05  Hedge trimmer (H-12)
  2026-10-06  Carpet cleaner (C-03)
Chloe Adebayo (07700 900311)
  2026-10-07  Pressure washer (P-07)
Sam Wu (07700 900319)
  2026-10-07  Ladder 3m (L-02)

4 loans, 3 members
```

Grouping, order, and the count line are as in `overdue` ("1 loan", "1 member" when there is one). With nothing due it prints `Nothing due DATE to DATE`. A bad `--on` or a `--within` outside 1 to 14 is a usage error (exit status 2).
