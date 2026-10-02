# hours

Brightwater Studio's timesheet tool. It reads the plain-text timesheets in `timesheets/` ([format](docs/timesheets.md)) and checks them or reports on them.

    $ node bin/hours.ts check timesheets/2026-09-*.txt
    $ node bin/hours.ts report --by client --from 2026-09-01 --to 2026-09-30 timesheets/2026-09-*.txt

hours is TypeScript that Node runs directly (Node 23.6 or later strips the types; there is no build step), and it has no dependencies. Keep to syntax Node can strip: no enums, namespaces, or constructor parameter properties, and `import type` for types. `tsconfig.json` is there for editors. `npm install -g .` puts `hours` on your PATH; it installs `bin/` and `src/`.

## Commands

- `hours check FILE...`: every line is an entry, and no two time ranges on the same day overlap within a file. Prints `FILE: N entries, h:mm` for each good file; problems go to standard error, and the exit status is 1.
- `hours report [--from DATE] [--to DATE] [--by project|client|date] FILE...`: time per project (or client, or date), with a total.

Exit status 2 means the command line was wrong.

## Layout

- `bin/hours.ts`: the command.
- `src/cli.ts`: dispatch to the commands in `src/commands/`, each of which returns a `Result` (`src/result.ts`).
- `src/timesheet.ts`: reading timesheets; `src/duration.ts` and `src/dates.ts`: times and dates; `src/table.ts`: plain-text tables.
- `test/`: tests, run with `npm test` (`node --test`).

## Month-end invoices

Invoices are made outside hours for now. On the first of the month `ops/month-end.sh` runs `scripts/invoice.py` (Python 3) for every client in the rate card, `rates.txt` ([format](docs/rates.md)), and writes `out/invoices/CLIENT-MONTH.txt`, which Dana pastes into the accounting system. Its tests: `python3 -m unittest discover -s scripts`.
