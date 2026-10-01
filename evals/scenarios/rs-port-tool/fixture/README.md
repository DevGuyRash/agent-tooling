# reqstat

Summarizes the logfmt access logs our edge proxies write: request counts, error rates, latency percentiles, and bytes served, grouped by route, path, status class, or method. The nightly ops job runs it on each proxy's log and diffs the report against the previous night's; the latency dashboard scrapes the CSV output.

```
reqstat [--by route|path|status|method] [--since TS] [--until TS]
        [--min-count N] [--sort count|p95|errors|name] [--top N]
        [--format table|csv] [--strict] [FILE ...]
```

Files are read in order; with no FILE, or for `-`, it reads standard input.

```
$ python3 -m reqstat --top 3 tests/data/sample.log
ROUTE               COUNT  ERR%   P50     P95     P99     MAX     BYTES
GET /api/users/:id      8  25.0  13.0  1200.0  1200.0  1200.0  13.9 KiB
GET /healthz            4   0.0   0.4     0.4     0.4     0.4       8 B
POST /api/orders        3  33.3  84.3  2004.0  2004.0  2004.0     738 B
-- 22 requests in 8 groups (3 shown), 3 malformed lines skipped, 2026-09-14T08:00:01Z .. 2026-09-14T08:00:59Z
```

## Log format

One request per line, as `key=value` pairs separated by spaces or tabs:

```
ts=2026-09-14T08:00:01Z method=GET path=/api/users/42 status=200 dur=12.5ms bytes=1830 ua="curl/8.9.1"
```

| key | required | value |
| --- | --- | --- |
| `ts` | yes | UTC time, `YYYY-MM-DDTHH:MM:SSZ` |
| `method` | yes | upper-case HTTP method |
| `path` | yes | request path, starting with `/`; any query string is ignored |
| `status` | yes | HTTP status, 100 to 599 |
| `dur` | yes | duration with a unit: `us`, `ms`, or `s` (`350us`, `12.5ms`, `1.2s`), to whole microseconds |
| `bytes` | no | response size in bytes (default 0) |

Values containing spaces are double-quoted; inside quotes a backslash makes the next character literal. Other keys are ignored. Blank lines and lines starting with `#` are skipped. A line that is not a valid record is counted as malformed and skipped; `--strict` stops at the first one instead (exit status 1).

## Report

- Paths are normalized before grouping: the query string is dropped, empty segments are collapsed, numeric segments become `:id`, and UUID segments become `:uuid`.
- Errors are responses with status 500 or above.
- P50, P95, and P99 are nearest-rank percentiles; latencies are in milliseconds.
- `--since` is inclusive and `--until` exclusive; both take `YYYY-MM-DD` (midnight UTC) or a full timestamp.
- Rows are sorted by request count unless `--sort` says otherwise, ties by name.
- `--format csv` prints raw numbers (bytes unscaled) and no footer.

All arithmetic is integer, with displayed fractions rounded half up, so the same log always gives byte-identical output.

## Development

```
python3 -m unittest discover -s tests -t .
```
