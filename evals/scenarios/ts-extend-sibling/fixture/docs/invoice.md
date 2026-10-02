# hours invoice

Dana, 2026-09-28. So that we can bill from `hours` instead of fixing up the month-end files by hand: they still bill the time we mark `+nobill`, and they only do whole months.

    hours invoice --client CLIENT --rates FILE --month YYYY-MM TIMESHEET...
    hours invoice --client CLIENT --rates FILE --from DATE --to DATE TIMESHEET...

`invoice` bills one client's time for one period. FILE is the rate card the month-end invoices use (`rates.txt`; the format is in [rates.md](rates.md)). The timesheets are read exactly as `hours report` reads them ([timesheets.md](timesheets.md)).

## What gets billed

- An entry belongs to CLIENT when the client part of its project (`acme` in `acme/site`) is CLIENT.
- The period is the calendar month given with `--month`, or the days from `--from` to `--to`, both included. Entries on other days are left out.
- An entry whose note has `+nobill` in it as a word of its own (the words of a note are separated by spaces or tabs) is not billed. Its time only goes on the "Not billed" line.
- Every other entry of the client in the period is billed. Its time is rounded **up** to a whole multiple of the client's `increment`, and then, if it is still less than the client's `minimum`, raised to the minimum. Each entry is rounded on its own, before anything is added up.
- A project is billed at its own `rate.PROJECT` from the rate card if there is one, otherwise at the client's `rate`.

## Amounts

Amounts are in the client's currency and exact to the cent. Nothing may pick up floating-point error.

- A project's amount is its billed minutes added up, times its hourly rate, divided by 60, rounded to the cent, with half a cent rounded up.
- The subtotal is the sum of the project amounts.
- The tax is the subtotal times the client's `tax` percentage, divided by 100, rounded to the cent the same way. There is no tax line when the client's tax is 0.
- The total is the subtotal plus the tax.

## Output

September 2026 for Acme, from the timesheets in this repository:

    $ hours invoice --client acme --rates rates.txt --month 2026-09 timesheets/2026-09-*.txt
    Invoice for Acme Outdoor GmbH (acme)
    Period: 2026-09-01 to 2026-09-30
    Currency: EUR

    Project     Entries   Time  Billed    Rate   Amount
    acme/brand        4   3:35    4:00  140.00   560.00
    acme/site        10  11:40   13:00  118.50  1540.50

    Subtotal  2100.50
    Tax 19%    399.10
    Total     2499.60

    Not billed: 1:10 in 2 entries

Line by line:

1. `Invoice for NAME (CLIENT)`, NAME as in the rate card.
2. `Period: FIRST to LAST`, the first and the last day of the period.
3. `Currency: CODE`.
4. An empty line.
5. The project table: a header row (`Project`, `Entries`, `Time`, `Billed`, `Rate`, `Amount`), then a row for each project with at least one billed entry, in alphabetical order. Entries counts the project's billed entries; Time is their time as the timesheets give it and Billed their rounded time, both in hours and minutes (`h:mm`, as in `hours report`); Rate and Amount have two decimals. It is laid out like the `hours report` table: columns two spaces apart, each as wide as its widest cell, the header included; Project left-aligned and the other columns right-aligned, the header row too; no spaces at the end of a line.
6. An empty line.
7. The totals: `Subtotal`, then `Tax T%` unless the tax is 0 (T is the percentage without trailing zeros: `19`, `7.7`, `8.25`), then `Total`, laid out the same way as two columns: the label left-aligned and the amount right-aligned.
8. If the client has entries in the period that are not billed: an empty line and `Not billed: h:mm in N entries` (`1 entry` when there is one).

When the client has no billed entries in the period, the single line `Nothing to bill.` takes the place of the project table and the totals; the "Not billed" line still follows it when there is one.

## Errors

Nothing goes to standard output when the command fails.

- Exit status 2, with a message on standard error that starts `hours invoice:`, when the command line is wrong: no `--client` or no `--rates`, neither or both of `--month` and `--from`/`--to`, `--from` without `--to` or the other way round, a month or date that is not a real one written as above, `--from` after `--to`, an unknown option, or no timesheet.
- Exit status 1 when the rate card or a timesheet cannot be read (`hours invoice: cannot read FILE`, then the reason), when the rate card has a mistake (the message names the file and the line, `FILE:LINE: ...`, as rates.md says), when CLIENT is not in the rate card (`hours invoice: no client "CLIENT" in FILE`), or when a timesheet has a mistake (`FILE:LINE: ...`, as `hours report` says it).

The command line is checked first, then the rate card, then the client, then the timesheets in the order given, and only the first mistake found is reported.

The month-end invoices keep being made the way they are today until we have compared `hours invoice` with them for a couple of months.
