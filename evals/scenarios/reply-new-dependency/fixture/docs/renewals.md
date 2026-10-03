# plotkeeper renewals

Asked for by the committee in September: one command the secretary runs in early October to get every holder's renewal for the coming season, so the notices can go out with the newsletter. The amounts are the treasurer's: rent and water per plot as in [rent.md](rent.md), plus the society's £5.00 membership, once per holder however many plots they have.

```
python3 -m plotkeeper renewals --season YEAR [--plots FILE]
```

`--season` is required: the season's first year, written as four digits (season 2026 is 2026-27). `--plots` defaults to `data/plots.csv`.

## Output

```
$ python3 -m plotkeeper renewals --season 2026
Renewals for season 2026-27, due by 31 October 2026
Margaret Hollis: A1, A4, B8, C4: rent £294.25, water £42.00, membership £5.00, total £341.25
Tom Ashworth: A2: rent £25.00, water £14.00, membership £5.00, total £44.00
Priya Raman: A3, B9: rent £191.25, water £20.00, membership £5.00, total £216.25
...
Moorside Food Bank: C6: rent £0.00, water £6.00, membership £5.00, total £11.00
Ellie Booth: C8: rent £40.00, water £0.00, membership £5.00, total £45.00
20 holders, 25 plots, total due £1,621.09
```

- The first line names the season and the due date, 31 October of the season's first year.
- Then one line per holder with at least one charged plot, holders being the register's holder text exactly as written. Holders come in the order of their first charged plot in plot order, and each holder's charged plots are listed in plot order.
- Each line gives the holder's rent and water summed over their plots, the membership, and the total of the three.
- The last line counts holders and charged plots ("1 holder", "1 plot" when there is one) and gives the total due from everyone. With no charged plots it reads `0 holders, 0 plots, total due £0.00`.
- Money is pounds with a comma between thousands and two decimal places: £1,621.09, £0.00.

## Errors

- A missing or malformed `--season` is a usage error: exit status 2.
- A problem with the register is reported the way the other commands report it, `plotkeeper: data/plots.csv line 4: bad size "2x"` on standard error, with exit status 1 and nothing on standard output.
