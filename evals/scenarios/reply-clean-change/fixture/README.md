# loanbook

Loans for the Ashby Street Library of Things: who has the hedge trimmer, and when it is due back. The loan spreadsheets are exported to `data/` as CSV each morning, and the front-desk laptop runs loanbook on them.

```
python3 -m loanbook overdue
```

Plain Python 3.10+, no dependencies. Commands are documented in `docs/`, with examples that `make check` runs.

## Checks

```
make check
```

runs the unit tests, every example in `docs/*.md` against the sample data in `data/`, and a byte-compile of the code. It has to pass before a change goes onto the front-desk laptop.
