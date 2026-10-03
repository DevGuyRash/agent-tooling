# How rent is worked out

Dev wrote `tools/rent.pl` in 2019 for the treasurer's bank sheet, and the treasurer banks against what it prints:

```
$ perl tools/rent.pl --season 2026 data/plots.csv
plot	holder	rent	water
A1	Margaret Hollis	5000	1400
...
total		61234	14200
```

Amounts are in pence. This page writes down the rules the script follows, as agreed at the 2023 and 2024 AGMs.

## The season

Season 2026 runs from 1 October 2026 to 30 September 2027 and is written "2026-27". Rent for a season is due by 31 October at its start.

## Which plots are charged

Every plot in the register with a holder, unless the holder's start date is after the season ends. Vacant plots are not charged.

## Rent for one plot

Work through the steps in this order, in whole pence:

1. **Base rent.** Full and half plots pay by area: 40p a square metre for the first 125 m², and 28p a square metre for the rest. A raised bed is £18.00 whatever its size. Community plots are rent-free.
2. **Lower field.** Plots on site C (the lower field, which floods every winter) get 20% off: multiply by 0.8 and round to the nearest penny.
3. **Second plots.** A holder's second and later full plots, counting their charged full plots in plot order, pay 25% more, rounded up to the next penny. Half plots, raised beds, and community plots do not count and are never surcharged.
4. **Concession.** Holders with a concession pay half, a half penny rounding up.
5. **Joining part-way.** A holder whose start date is after 1 October of the season pays for whole months: the month they joined through September, out of 12, rounded up to the next penny. Joining any time in October counts as the whole year.
6. **Minimum.** A full plot, half plot, or raised bed never pays less than £12.00 after the steps above. Community plots stay rent-free.

## Water

Water is charged per plot on top of rent and is never reduced or split by month: £14.00 for a plot with its own standpipe (`Y` in the register) and £6.00 for a plot that shares a trough (`T`).

## Plot order

Plots are ordered by site letter, then by plot number as a number, so A2 comes before A10.
