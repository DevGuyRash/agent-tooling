# checkout-service

Handles cart checkout and card payments for the storefront. Production logs for incident reviews are exported to `incident/`, one file per source, timestamps in UTC.

- `src/checkout/` — service code and configuration
- `incident/app.log` — checkout application log
- `incident/deploys.log` — production deploy events
- `incident/cron.log` — scheduled job runs
- `incident/db.log` — database server log
