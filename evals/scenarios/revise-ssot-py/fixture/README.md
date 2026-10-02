# circdesk

Circulation desk tools for Elmbrook Public Library, run on the circulation box against the library system's nightly exports (docs/export-format.md). Python 3.10 or later, standard library only.

```
python3 -m circdesk receipt LOANS.csv LOAN_ID                          the desk receipt for a returned item
python3 -m circdesk notices LOANS.csv PATRONS.csv [--on DATE]          tonight's overdue notices, for the mailer
python3 -m circdesk account LOANS.csv PATRONS.csv PATRON_ID [--on DATE]  what a patron owes, for the kiosk
```

`--on` is the day fines are worked out for; it defaults to today. The notices job runs at 02:00 from cron and hands its output to the mailer; the kiosk calls `account` when a patron scans their card.

Fines follow the board's policy in docs/fines.md.

Problems with an export (a missing file or column, a bad date, an unknown loan, patron, or category) print `circdesk: ...` and exit 1; a bad command line exits 2.

## Tests

```
python3 -m unittest discover -s tests -t .
```
