# acctreport

Sales reports for the account team, run against the sales database (SQLite). Each report's query lives in `acctreport/sql/`; `acctreport/schema.sql` describes the tables.

Python 3.10 or later with the standard library; nothing to install.

## Dev database

`data/dev_seed.sql` is an anonymized snapshot of production. Build a local database from it:

    python3 -m acctreport load-dev            # writes data/dev.db (--force to rebuild)

## Customer activity report

    python3 -m acctreport activity --start 2026-08-01 --end 2026-09-01

One row per customer for the period from `--start` (inclusive) to `--end` (exclusive), highest revenue first, ties by customer id. The account managers go through it every month to see who is ordering and who has gone quiet.

| Column | Meaning |
|---|---|
| `customer_id`, `customer` | The customer. |
| `account_manager` | The customer's current account manager: the manager on their most recent assignment (latest `assigned_on`; when two assignments share that date, the one with the higher `assignment_id`). Empty if the customer has never been assigned. |
| `order_count` | Orders the customer placed in the period. |
| `revenue_cents` | Sum of `total_cents` over those orders. |
| `last_order_date` | Date of the latest of those orders; empty when there are none. |

## Tests

    python3 -m unittest discover -s tests -t .
