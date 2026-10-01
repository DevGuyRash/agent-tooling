# Alert history exports

The paging service exports the alerts it delivered as tab-separated text (Reports, then History, then "Download TSV"). `history/` keeps one export per quarter, and `pagerlog` reads them.

```
time	alert	receivers	labels
2026-07-01T03:12:44Z	DiskFull	storage-oncall	service=db-orders,severity=critical,team=storage
2026-07-01T03:14:02Z	ApiLatency	payments-oncall,payments-tickets	env=prod,service=checkout,team=payments
2026-07-01T09:30:00Z	CertExpiry	platform-tickets	-
```

- The first line is the header, exactly as above.
- Every other line is one alert, with four fields separated by tabs:
  - `time`: when it fired, in UTC, as `YYYY-MM-DDTHH:MM:SSZ`.
  - `alert`: its name, letters, digits, and `_`.
  - `receivers`: the receivers it was delivered to, separated by commas, each named once; a receiver name is lowercase letters, digits, and `-`, starting with a letter or digit.
  - `labels`: its labels as `name=value`, separated by commas, or `-` when it has none. A name is lowercase letters, digits, and `_`, not starting with a digit, and appears at most once; a value is not empty and has no spaces, tabs, or commas. `alertname` never appears: the service exports it as the `alert` field.
- Empty lines are skipped. Lines may end in LF or CRLF. Alerts are not necessarily in time order.

## Errors

`pagerlog` reports the first problem as `FILE: line N: MESSAGE`:

| Message | When |
| --- | --- |
| `bad header` | The first line is not the header (an empty file included). |
| `expected 4 fields, found K` | |
| `bad time "TEXT"` | Not a valid UTC time in that form. |
| `bad alert name "TEXT"` | |
| `bad receivers "TEXT"` | An empty or invalid name, or a name given twice. |
| `bad label "TEXT"` | TEXT is the `name=value` item that is not valid. |
| `label "NAME" given twice` | |
| `label "alertname" is reserved` | |
