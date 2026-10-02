# deskd

The support desk's ticket service. It reads the ticketing system's nightly dump (one JSON object per ticket per line) and serves it to the support dashboard as JSON; ops scripts use the same views through the command line.

```sh
python3 -m deskd serve --store /data/tickets.jsonl --port 8080   # GET /tickets, GET /tickets/ID
python3 -m deskd show --store tickets.jsonl 4182                  # one ticket, as the API gives it
python3 -m deskd export --store tickets.jsonl                     # every ticket, one JSON object per line
python3 -m deskd list --store tickets.jsonl --status open
```

`--config DIR` (before the command; default `config`) is the directory holding `deskd.conf` (the team name and the priority labels) and support's calendar files (see `docs/sla.md`).

Production runs the image built from the `Dockerfile`; the dashboard reads the API and the nightly export.

## Tests

```sh
python3 -m unittest
```

## tools/

Support's own scripts, which they run from their laptops. `tools/sla_due.pl` works out first-response due times (`docs/sla.md`); its tests run with `prove tools/t` from the repository root.
