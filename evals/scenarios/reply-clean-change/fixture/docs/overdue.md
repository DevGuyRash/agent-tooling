# loanbook overdue

Loans that are past their due date and not yet returned, grouped by member so a volunteer can work down the list with the phone.

```
python3 -m loanbook [--data DIR] overdue [--on DATE]
```

`--on` is the day to check (default today). A loan is overdue when its due date is before that day and it has no returned date.

```
$ python3 -m loanbook overdue --on 2026-10-05
Overdue on 2026-10-05

Tom Okoro (07700 900322)
  2026-09-30  Cordless drill (D-01), 5 days late
  2026-10-03  Tile cutter (T-09), 2 days late
Bogdan Nowak (07700 900307)
  2026-10-04  Gazebo 3x3m (G-04), 1 day late

3 loans, 2 members
```

Members come in order of their earliest due date, then by name; each member's loans by due date, then item. With nothing overdue it prints `Nothing overdue on DATE`.
