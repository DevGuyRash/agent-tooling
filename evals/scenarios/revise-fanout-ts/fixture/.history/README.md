# plugctl

Command-line tools the Brightwater Charge operations team uses to look at the city's public chargers. plugctl talks to the charge-point hub, which relays each request to a charger over its cellular modem; the part of the hub's protocol we use is in [docs/hub-protocol.md](docs/hub-protocol.md).

TypeScript run directly by Node (22.18 or newer, which strips the types itself); no dependencies and no build step.

## Use

```bash
node bin/plugctl.ts list                    # every charger ID, sorted
node bin/plugctl.ts read CP-0412 CP-0007    # connectors free right now
```

The hub's address comes from `--hub HOST:PORT`, else `PLUGCTL_HUB`, else `127.0.0.1:7300`.

`read` prints one line per charger, in the order given, `CP-0412: 1 of 2 free, 22 kW`, and exits 1 with a message on standard error when the hub replies with an error or cannot be reached.

Usage errors exit 2.

## Layout

- `src/hub.ts`: the hub client (`listChargers`, `chargerStatus`, `HubError`).
- `src/cli.ts`: the commands.
- `test/`: tests for `node --test`, with `test/fakehub.ts` standing in for the hub.

## Tests

```bash
npm test     # or: node --test
```
