# ledgerkit

Imports the card processor's nightly settlement export (format: [docs/processor-export.md](docs/processor-export.md)) into the chain's transaction ledger, and reports daily totals per store from it.

The ledger lives on the finance share as `ledger.csv`: a header line, then one line per card transaction (`ts,store,terminal,card,amount_cents`, see `src/ledger.ts`). The nightly job runs `ledgerkit import` on the new export; the finance team runs `ledgerkit totals` for the morning report.

## Commands

```
node bin/ledgerkit.ts import EXPORT.csv --ledger LEDGER.csv
node bin/ledgerkit.ts totals --ledger LEDGER.csv [--from YYYY-MM-DD] [--to YYYY-MM-DD]
node bin/ledgerkit.ts check --ledger LEDGER.csv
```

- `import` checks the whole export first; if any line is bad it prints every problem and changes nothing (exit 1). Otherwise it appends the export's transactions to the ledger in the export's order, creating the ledger if it does not exist.
- `totals` prints sales, refunds, and net amount per day and store.
- `check` validates every ledger line.

Usage errors exit 2; unreadable files exit 1.

## Development

Plain TypeScript, run directly by Node 24 or newer (type stripping), with no dependencies. Tests use `node:test`:

```
npm test        # or: node --test
```
