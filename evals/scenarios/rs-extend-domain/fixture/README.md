# kittiwake-oncall

On-call tooling for Kittiwake's platform team: the routing files the paging service loads, `pagerlog` for reports on the alerts it delivered, and the script on-call uses to try routing changes.

| Path | What it is |
| --- | --- |
| `routing/` | where the paging service sends alerts ([format](docs/routing.md)); deployed on merge |
| `history/` | the paging service's alert history, one export per quarter ([format](docs/history.md)) |
| `crates/history` | reads history exports |
| `crates/table` | plain-text tables for pagerlog's reports |
| `crates/pagerlog` | the `pagerlog` command-line tool |
| `tools/routes.py` | checks routing files and shows where an alert would go |

## pagerlog

```
pagerlog check HISTORY                            check an export and say what it covers
pagerlog receivers [--sort alerts|name] HISTORY   alerts per receiver, and how many at night and at weekends
pagerlog top [--limit N] HISTORY                  the alerts that fired most
```

Usage errors exit with status 2 and other errors with status 1; messages go to standard error and start with `pagerlog: `.

## Changing routing

The paging service refuses a deploy whose routing files have an error, so before merging a change under `routing/`, check it and try the alerts it is meant to move:

```
python3 tools/routes.py check routing/main.routes
python3 tools/routes.py test routing/main.routes alertname=DiskFull service=db-orders team=storage severity=critical
python3 tools/routes.py test routing/main.routes --at 2026-10-03T02:15:00Z alertname=ApiLatency team=payments env=prod
python3 tools/routes.py tree routing/main.routes
```

`check` reports the first error, `test` prints the receivers an alert with those labels would go to (now, or at `--at`, in UTC), and `tree` prints every route with the receiver it sends to. The script's tests run with `python3 -m unittest discover -s tools`.

## Building and testing

Standard library only: the on-call laptops build from this repository, often with no network (`.cargo/config.toml` keeps cargo offline), so please don't add dependencies.

```
cargo build --release
cargo test
cargo install --path crates/pagerlog --offline
```
