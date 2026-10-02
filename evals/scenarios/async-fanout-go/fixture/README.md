# farmctl

Command-line tool for the Hollow Creek solar farm. farmctl reads the inverters through the plant's SCADA gateway, using the gateway's text protocol ([docs/gateway.md](docs/gateway.md)).

Go standard library only.

## Build and use

```bash
go build ./cmd/farmctl
./farmctl list                    # every inverter, sorted by name
./farmctl read INV-014 INV-002    # today's energy and the output right now
```

The gateway's address comes from `-gateway host:port`, else `FARMCTL_GATEWAY`, else `127.0.0.1:5020`.

`read` prints one line per inverter, `INV-014: 4821 Wh today, 1520 W now`. When the gateway answers with an error it prints `farmctl: INV-014: error 503 inverter fault` on standard error and exits 1.

## Layout

- `internal/gateway`: the gateway client (`Client.Inverters`, `Client.Read`, `Reading`, `Error`).
- `internal/fakegw`: a fake gateway for tests.
- `cmd/farmctl`: the command.

## Tests

```bash
go test ./...
```
