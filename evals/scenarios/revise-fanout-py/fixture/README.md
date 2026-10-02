# coldctl

Command-line tools the Larchmont Grocers distribution center (DC2) uses to read its refrigeration: display cases, walk-in coolers, and freezer bays. coldctl talks to the BMS gateway, which relays each request to a unit's controller over the field bus; the part of the gateway's API we use is in [docs/bms-gateway.md](docs/bms-gateway.md).

Standard library only, Python 3.10 or newer.

## Use

```bash
python3 -m coldctl units                 # every unit: ID and zone, in ID order
python3 -m coldctl temp U-0412 U-0007    # temperature and setpoint right now
python3 -m coldctl check                 # every unit, for the food-safety monitor
```

The gateway's address comes from `--gateway URL`, else `COLDCTL_GATEWAY`, else `http://127.0.0.1:8640`.

`temp` prints one line per unit, in the order given, `U-0412: -19.4 C (setpoint -20.0 C)` (with `, defrosting` at the end while the unit runs a defrost cycle), and exits 1 with a message on standard error when the gateway answers with an error or cannot be reached.

`check` reads every unit and prints one line per unit in ID order: the line `temp` prints, `U-0412: no answer` when the unit's controller has not answered within 2 seconds, or `U-0412: failed (HTTP 502)` when the gateway answers with an error. A last line counts them, `checked 203 units: 196 read, 4 no answer, 3 failed`. It exits 0 when every unit was read, 1 otherwise, and 2 when it cannot get the unit list. The food-safety monitor runs it every five minutes and parses its output.

## Layout

- `coldctl/gateway.py`: the gateway client (`list_units`, `unit_reading`, `GatewayError`, `NoAnswer`).
- `coldctl/cli.py`: the commands.
- `tests/`: unit tests, with `tests/fakegateway.py` standing in for the gateway.

## Tests

```bash
python3 -m unittest
```
