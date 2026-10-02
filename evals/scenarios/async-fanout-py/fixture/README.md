# dockctl

Command-line tools the Riverbend Bikes ops team uses to look at the dock network. dockctl talks to the dock gateway, which relays requests to the docks over their cellular modems; the part of the gateway's API we use is in [docs/gateway-api.md](docs/gateway-api.md).

Standard library only, Python 3.10 or newer.

## Use

```bash
python3 -m dockctl list                 # every dock: ID and name, in ID order
python3 -m dockctl show D-0042 D-0007   # bikes and free slots right now
```

The gateway's address comes from `--gateway URL`, else `DOCKCTL_GATEWAY`, else `http://127.0.0.1:8470`.

`show` prints one line per dock, `D-0042: 7 bikes, 12 free`, and exits 1 with a message on standard error when the gateway answers with an error or cannot be reached.

## Layout

- `dockctl/gateway.py`: the gateway client (`list_docks`, `dock_status`, `GatewayError`).
- `dockctl/cli.py`: the commands.
- `tests/`: unit tests, with `tests/fakegateway.py` standing in for the gateway.

## Tests

```bash
python3 -m unittest
```
