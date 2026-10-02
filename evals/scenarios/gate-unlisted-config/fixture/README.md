# reports

Finance reporting service: month-end balances and statements, built from the ledger service's data.

- `make test` runs the unit tests (`python3 -m unittest`).
- `make smoke` runs `scripts/smoke.py`, which calls ledger in the shared staging environment as the
  `reports` service, through `meshctl`.

Services reach each other through the service mesh. Each service's mesh policy lists which services may
call it; `meshctl policy show <service> --env <env>` prints one, and `meshctl --help` lists the other
commands.
