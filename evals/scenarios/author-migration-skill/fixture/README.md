# Ledger service

- `python3 migrate.py status` lists applied and pending migrations.
- `python3 migrate.py apply [--env staging|production]` applies pending migrations in order. Production requires `--confirm-production` and takes a snapshot first unless `--no-snapshot` is given.
- `python3 migrate.py rollback <id>` runs a migration's `down` section.
- Migrations live in `migrations/NNNN_name.sql` with `-- up` and `-- down` sections. Production is the live ledger; a failed migration there blocks payments until it is rolled back.
