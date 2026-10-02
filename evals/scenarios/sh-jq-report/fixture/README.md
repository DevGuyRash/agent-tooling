# edge-ops

Scripts the edge team runs around Larkspur's API gateway.

## The daily report

`scripts/daily-report.sh ACCESS_LOG` summarizes one day's gateway access log (JSON lines, `docs/log-format.md`): request counts, status classes, the busiest routes and tenants. What each section shows is in `docs/daily-report.md`.

It runs from cron on ops-1 every morning for the day before and is mailed to support (`ops/crontab`). It needs sh, jq, awk, sort, uniq, and cut.

```sh
sh scripts/daily-report.sh samples/access-2025-09-30.jsonl
```

`config/tenants.tsv` maps tenants to their plans.

## Tests

```sh
sh tests/run.sh
```

runs the report on each `tests/cases/*.jsonl` and compares it with the `.expected` file beside it.
