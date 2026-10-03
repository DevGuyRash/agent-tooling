# berthbook

Harbourline Marina's booking exports. The harbour office runs the nightly berth sheet from cron:

```
python3 -m berthbook export --date 2026-08-15 > sheets/2026-08-15.csv
```

berthbook is plain Python 3.10+ with no dependencies. It talks to the Harbourline Booking API ([docs/api.md](docs/api.md)); set `BERTHBOOK_API` to point it somewhere other than production.

## Tests

```
make test          # unit tests, offline
make integration   # against the booking simulator (needs Docker)
```

`make integration` starts Harbourline's booking simulator with Docker (`compose.integration.yml`), runs `tests/integration` against it on port 8089, and stops it again.

## Releasing

Both `make test` and `make integration` must pass on the commit you tag. Move the "Unreleased" notes in CHANGELOG.md under the new version, bump `berthbook/__init__.py`, tag `vX.Y.Z`, and push the tag; the harbour office's machine picks up tags overnight.
