# ledgerline

Normalize bank CSV exports (Chase, Ally, Schwab) into one ledger format.

```sh
ledgerline normalize --bank chase statement.csv          # table
ledgerline normalize --bank ally --json savings.csv      # JSON for other tools
```

Each transaction has an ISO date, a cleaned description, a signed decimal amount (positive is money in), and a category (`debit`, `credit`, or `income`).
