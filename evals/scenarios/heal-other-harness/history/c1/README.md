# meterwatch

Roll up API usage events into daily totals and invoices.

```sh
meterwatch daily events.jsonl
meterwatch daily events.jsonl --key acme
meterwatch invoice events.jsonl --rate 0.0025 --from 2026-03-01 --to 2026-03-31
```

Events are JSON lines such as `{"ts": 1772325000, "key": "acme", "units": 4}`; `ts` is seconds since the Unix epoch.

## Days are UTC days

An event belongs to the UTC calendar day of its `ts`, whatever time zone the machine running meterwatch is set to, so every teammate's report and every invoice agree. `--from` and `--to` take UTC days.
