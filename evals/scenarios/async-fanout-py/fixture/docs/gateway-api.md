# Dock gateway API (v1)

The dock gateway sits between our systems and the docks. Every dock reports to it over a cellular modem, and the gateway answers HTTP on port 8470 inside the ops network. This page is the part of the vendor's reference we use, with our notes.

## Endpoints

### `GET /v1/docks`

Every dock the gateway knows, in no particular order. Answered from the gateway's own table, usually within 50 ms.

```json
{"docks": [{"id": "D-0042", "name": "Riverside Park"}, {"id": "D-0007", "name": "Mill Street"}]}
```

Dock IDs are `D-` followed by four digits.

### `GET /v1/docks/{id}/status`

The dock's current state, read live from the dock over its modem.

```json
{"id": "D-0042", "bikes": 7, "free": 12, "read_at": "2026-09-30T08:14:03Z"}
```

`bikes` is the number of bikes docked and available, `free` the number of empty slots. Other fields may be added; ignore what you don't use.

A status read usually takes 50 to 300 ms. Docks on a weak signal can take over a second. When a dock does not answer at all (modem down, dock without power), the gateway keeps waiting for it for up to 60 seconds and then answers `504`.

Errors:

| Status | Meaning |
| --- | --- |
| 404 | No dock with that ID. |
| 500 | The dock answered with a fault. |
| 502 | The dock's answer was garbled. |
| 504 | The dock did not answer within 60 seconds. |

## Limits

Each client may have at most **16 requests in progress** at a time. A request that arrives while 16 requests from the same client are still in progress is answered `429 Too Many Requests` at once, and a client that keeps going over the limit is blocked for an hour.

A request counts against the limit until the gateway has sent its response, or until the client closes the connection.

## Our notes

- Ops reaches the gateway at `http://gw.ops.riverbend.example:8470`; locally we point `DOCKCTL_GATEWAY` at a tunnel.
- The gateway has no test instance. `tests/fakegateway.py` imitates the endpoints above for our tests.
