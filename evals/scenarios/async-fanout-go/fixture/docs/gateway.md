# SCADA gateway protocol

The plant's SCADA gateway is the only way onto the inverters' RS-485 bus from the plant network. It listens on TCP port 5020. This is the part of the vendor's manual (section 7, "Text protocol") that farmctl uses, with our notes.

## Requests

Each connection carries one request: the client sends one line ending in `\n`, the gateway sends its reply and closes the connection. A client that closes the connection before the reply, or shuts down only its sending side, has hung up: the gateway drops the request and sends nothing.

### `LIST`

```
LIST
OK 3
INV-014
INV-002
INV-131
```

The first reply line gives the number of inverters, followed by one name per line in bus order. Answered from the gateway's own table, at once.

### `READ <inverter>`

```
READ INV-014
OK INV-014 4821 1520
```

Today's energy in Wh (since local midnight) and the output right now in W. The gateway relays the request to the inverter over the bus, so the reply usually takes 30 to 150 ms; inverters at the far end of a long string can take over a second.

An inverter that does not answer at all (tripped, comms card down) gets no reply on the bus. The gateway keeps the connection open while it waits, for up to 30 seconds, and then replies `ERR 504 inverter timeout`.

### Errors

`ERR <code> <text>`, for example:

| Reply | Meaning |
| --- | --- |
| `ERR 404 unknown inverter` | No inverter by that name on the bus. |
| `ERR 502 bus error` | The inverter's answer was corrupted on the bus. |
| `ERR 503 inverter fault` | The inverter answered, but reports a fault. |
| `ERR 504 inverter timeout` | No answer within the gateway's 30 seconds. |

## Connection limit

The gateway accepts at most **16 TCP connections at a time**. A connection opened while 16 are already open is closed at once without a reply, and the gateway raises a comms alarm on the control-room SCADA screen.

A connection counts against the limit until the gateway has sent its reply, or until the client closes it.

## Our notes

- On site the gateway is `scada-gw.hollowcreek.example:5020`; from the office we tunnel to it and set `FARMCTL_GATEWAY`.
- There is no test gateway. `internal/fakegw` imitates the protocol above for our tests.
