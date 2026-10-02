# gatepass

Builds the turnstile file for an event at Northgate Park from the box office's sales export, and checks single codes at the gate. Each pass's check code is derived from the event's secret ([docs/codes.md](docs/codes.md)); the export's format is in [docs/sales-export.md](docs/sales-export.md), and how the job runs on event days in [docs/operations.md](docs/operations.md).

Go, standard library only.

## Use

```bash
go build ./cmd/gatepass
./gatepass build -event EVT-2026-0412 -key testdata/sample.key testdata/sample-sales.csv > turnstile.csv
./gatepass verify -event EVT-2026-0412 -key testdata/sample.key P-104233 0 M9FJ-7XD3-62MQ-W9NH
```

`build` prints the turnstile file on standard output and a summary on standard error, and exits 1 (writing nothing) when the export has a malformed row, naming its line. `verify` exits 0 when the code matches and 1 when it does not. Usage errors exit 2.

## Layout

- `internal/sales`: reads the export.
- `internal/passcode`: the code derivation and the event key.
- `internal/issue`: issue numbers, the turnstile list, and the file.
- `cmd/gatepass`: the commands.
- `testdata`: a sample export, key, and the turnstile file it gives.

## Tests

```bash
go test ./...
```
