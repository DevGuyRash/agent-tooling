# The processor's settlement export

Every night around 01:00 the card processor drops `settlement-YYYY-MM-DD.csv` on the SFTP share: the card transactions it settled for all our stores. `ledgerkit import` reads it.

```
Date,Time,Store,Terminal,Card,Amount,Type
2026-09-14,07:42,S07,2,************4821,4.50,SALE
2026-09-14,07:43,S07,1,************0193,9.75,SALE
2026-09-14,08:10,s12,3,************7730,4.25,REFUND
```

| Column | Meaning |
|---|---|
| `Date`, `Time` | When the card was used, in the store's local time, to the minute. |
| `Store` | Our store code, `S01` to `S30`. Older terminals send it in lower case. |
| `Terminal` | The till's number within the store. |
| `Card` | The card number, masked down to its last four digits. |
| `Amount` | Dollars with two decimals, always positive. |
| `Type` | `SALE` or `REFUND`. |

There is no transaction ID; the processor says it can't add one. Lines are ordered by date, time, store, and terminal. Files from some days have Windows line endings.

Since 2026-09-02 each export is rolling: it holds the last three days of transactions, not just the previous day, so that transactions settled late show up too.
