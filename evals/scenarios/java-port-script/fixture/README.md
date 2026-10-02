# platform-scripts

Reports the platform team runs against the CI system's exports.

## runner-usage

`scripts/runner-usage.sh` totals CI runner minutes per team from the nightly job export and compares them with each team's monthly budget.

```sh
scripts/runner-usage.sh -b budgets.txt -m 2026-09 jobs-2026-09.csv
scripts/runner-usage.sh -p macos -p arm64 -n 10 jobs-*.csv
ci-export --since 2026-09-01 | scripts/runner-usage.sh -b budgets.txt
```

Each job bills its seconds rounded up to whole minutes, with a minimum of one minute. The budget alert job runs it on the first of every month and pages the team leads when it exits 1 (a team over budget); finance imports the table into the chargeback sheet, so the layout is fixed.

The export is CSV without quoting, one job per line: `job_id,team,pool,date,seconds,status`. The budgets file has one `team minutes` line per team, `#` comments, and an optional `* minutes` line for teams without their own.

## Tests

`tests/run.sh` runs each case in `tests/cases` against the script and compares output and exit status exactly. Set `RUNNER_USAGE` to the command of another build to test that instead.
