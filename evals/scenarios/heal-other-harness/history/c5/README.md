# meterwatch

Roll up API usage events into daily totals and invoices.

```sh
meterwatch daily events.jsonl
meterwatch daily events.jsonl --key acme
meterwatch daily events.jsonl --total
meterwatch top events.jsonl -n 5
meterwatch invoice events.jsonl --rate 0.0025 --from 2026-03-01 --to 2026-03-31
```

Events are JSON lines such as `{"ts": 1772325000, "key": "acme", "units": 4}`; `ts` is seconds since the Unix epoch.

## Days are UTC days

An event belongs to the UTC calendar day of its `ts`, whatever time zone the machine running meterwatch is set to, so every teammate's report and every invoice agree. `--from` and `--to` take UTC days.

## Invoices

`--from` and `--to` are UTC days, and both are included. Each line is the day's units times `--rate`, rounded half up to the cent, so lines can differ by a cent from units times rate over the whole period.
