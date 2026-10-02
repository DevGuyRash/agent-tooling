# tapfare

The nightly fare run for Kestrel Valley Buses' contactless cards: it takes the back office's export of a service day's taps ([docs/tap-export.md](docs/tap-export.md)), works out what each tap costs under the fare rules ([docs/fares.md](docs/fares.md)), and writes the per-tap charges and the per-card debits that billing takes from the cards' accounts.

## Commands

```
node bin/tapfare.ts charge TAPS.csv --out DIR
node bin/tapfare.ts statement CHARGES.csv --card CARD
node bin/tapfare.ts check TAPS.csv
```

- `charge` checks the export, then writes `DIR/charges.csv` and `DIR/debits.csv` and prints a summary line. A bad line anywhere means nothing is written (exit 1).
- `statement` prints one card's day from a `charges.csv`, the way the customer-service desk reads it out.
- `check` only checks the export.

Usage errors exit 2; unreadable files exit 1.

`scripts/nightly.sh` is the cron job on fares-01.

## Development

Plain TypeScript, run directly by Node 24 or newer (type stripping), with no dependencies. Tests use `node:test`:

```
npm test        # or: node --test
```
