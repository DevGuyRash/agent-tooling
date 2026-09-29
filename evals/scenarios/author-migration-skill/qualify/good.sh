mkdir -p skills/db-migrations && cat > skills/db-migrations/SKILL.md <<'MD'
---
name: db-migrations
description: Create and apply this repo's SQL migrations with migrate.py, including production safety.
---

# DB Migrations

Migrations are `migrations/NNNN_name.sql` files with `-- up` and `-- down` sections; every new migration needs a working `down` so `python3 migrate.py rollback <id>` can undo it. Number it after the highest existing file.

Check state with `python3 migrate.py status`. Apply to staging with `python3 migrate.py apply --env staging` first.

Production is the live ledger and a failed migration blocks payments. You SHALL NOT apply to production unless the user asked for it; production needs `--confirm-production`, and you SHALL keep the automatic snapshot (never pass `--no-snapshot`).
MD
