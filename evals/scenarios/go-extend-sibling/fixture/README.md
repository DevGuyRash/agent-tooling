# bakctl

Tools for the backup tier: `bakctl` reads the snapshot catalog that the storage servers (store-01, store-02) export every night at 04:00 UTC and answers questions about it.

```sh
go build ./cmd/bakctl
./bakctl list --host db-1 catalog.tsv
./bakctl usage --by series catalog.tsv
./bakctl check catalog.tsv
curl -fsS http://store-01.internal:8420/v1/catalog.tsv | ./bakctl list -
```

Exit status is 0 on success, 1 when the catalog cannot be read or is invalid, and 2 for a usage error.

## Catalog format

One snapshot per line, seven tab-separated fields:

| Field | Value |
| --- | --- |
| id | unique snapshot id, such as `s-7f3a1c` |
| host | the machine the snapshot was taken on |
| set | the backup set (`pgdump`, `wal`, `etc`, `maildir`, ...) |
| created | RFC 3339 time with seconds and a zone (`2026-01-05T02:00:04Z`, `2026-01-14T01:30:00+02:00`) |
| bytes | stored size |
| state | `ok`, `partial` (upload not finished), or `failed` |
| tags | comma-separated tags, or `-` |

Blank lines and lines starting with `#` are ignored. A host and set together make a series.

## Layout

- `cmd/bakctl`: the command and its subcommands.
- `internal/catalog`: reads and validates catalogs.
- `internal/report`: the `list`, `usage`, and `check` output.
- `internal/humanize`: size formatting.
- `docs/`: specs for work in progress.

The module uses the standard library only; release builds run offline on the build host, so it cannot take third-party modules.

## Nightly prune

`ops/nightly-prune.sh` runs from cron on backup-01 at 04:30 UTC. It fetches the catalog, runs `scripts/retention.py` with the current policy (keep the last 3 snapshots, 14 daily, 8 weekly, 12 monthly) to pick the snapshots to delete, and deletes them through the storage API. It predates bakctl. `DRY_RUN=1` prints what it would delete; `scripts/retention.py --json` shows every decision when checking a policy by hand.

## Tests

```sh
go test ./...
python3 -m unittest discover -s scripts
```
