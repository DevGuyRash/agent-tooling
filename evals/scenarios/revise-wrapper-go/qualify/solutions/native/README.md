# ferry

Inchmara Ferries' tool for the crossing logs the ticket offices keep ([format](docs/log-format.md)).

```
ferry check LOG...                                   check logs and summarize each
ferry day DATE LOG...                                one day's sailings in departure order
ferry punctuality [--from DATE] [--to DATE] LOG...   punctuality figures per route (docs/punctuality.md)
```

Usage errors exit with status 2 and problems with the logs with status 1; messages go to standard error and start with `ferry: `.

| Path | What it is |
| --- | --- |
| `cmd/ferry` | the command |
| `internal/sailings` | reads and checks crossing logs |
| `internal/table` | plain-text tables |
| `logs/` | the week of 14 September, from every pier |

## Building and testing

Standard library only.

```
go build ./cmd/ferry
go test ./...
```
