# Charge-point hub protocol

Every public charger in the network reports to the operator's charge-point hub over a cellular modem, and the hub is the only way to reach the chargers from our network. It listens on TCP port 7300 inside the operations VPN. This page is the part of the hub vendor's integration guide (chapter 4, "Line protocol") that plugctl uses, with our notes.

## Requests

Each connection carries one request: the client sends one line ending in `\n`, the hub sends its reply and closes the connection. A client that closes the connection before the reply, or shuts down only its sending side, has hung up: the hub drops the request and sends nothing.

### `LIST`

```
LIST
OK 3
CP-0412
CP-0007
CP-0131
```

The first reply line gives the number of chargers, followed by one charger ID per line, in the hub's own order (the order they were commissioned). Answered from the hub's table, at once. Charger IDs are `CP-` followed by four digits.

### `STATUS <charger>`

```
STATUS CP-0412
OK CP-0412 2 1 22
```

The charger's number of connectors, how many of them are free right now, and its rated power in kW (a whole number or one decimal, such as `7.4`). The hub asks the charger over its cellular link, so the reply usually takes 30 to 150 ms; chargers on a weak signal can take over a second.

A charger that does not answer at all (modem down, charger without power) gets no reply from the hub until the hub gives up on it after 30 seconds and replies `ERR 504 charger timeout`. The hub keeps the connection open while it waits.

### Errors

`ERR <code> <text>`, for example:

| Reply | Meaning |
| --- | --- |
| `ERR 404 unknown charger` | No charger with that ID. |
| `ERR 502 garbled reply` | The charger's answer was corrupted on the cellular link. |
| `ERR 503 charger fault` | The charger answered, but reports a fault. |
| `ERR 504 charger timeout` | No answer within the hub's 30 seconds. |

## Connection limit

The hub accepts at most **16 TCP connections at a time** from one account. A connection opened while 16 are already open is closed at once without a reply, and an account that keeps going over the limit is suspended until the operator's support desk lifts the suspension (next business day).

A connection counts against the limit until the hub has sent its reply, or until the client closes it.

## Our notes

- The production hub is `hub.ops.brightwater-charge.example:7300`; from the office we tunnel to it and set `PLUGCTL_HUB`.
- There is no test hub. `test/fakehub.ts` imitates the protocol above for our tests.
