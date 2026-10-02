# BMS gateway API (v2)

The building-management (BMS) gateway is how anything outside the plant room reads the refrigeration controllers. Every display case, walk-in cooler, and freezer bay has a controller on the BMS field bus; the gateway answers HTTP on port 8640 on the operations network and relays each reading request to the unit's controller over the bus. This page is the part of the vendor's API reference we use, with our notes.

## Endpoints

### `GET /v2/units`

Every refrigeration unit the gateway knows, in no particular order. Answered from the gateway's own table, usually within 50 ms.

```json
{"units": [{"id": "U-0412", "zone": "Freezer B"}, {"id": "U-0007", "zone": "Dairy cooler"}]}
```

Unit IDs are `U-` followed by four digits.

### `GET /v2/units/{id}/reading`

The unit's current reading, taken live from its controller over the field bus.

```json
{"id": "U-0412", "temp_c": -19.4, "setpoint_c": -20.0, "defrost": false, "read_at": "2026-09-30T02:14:03Z"}
```

`temp_c` is the air temperature in the unit and `setpoint_c` the temperature its controller holds it to, both in degrees Celsius to one decimal place. `defrost` is true while the unit runs a defrost cycle, when its temperature sits a few degrees above setpoint for a while; that is expected. Other fields may be added; ignore what you don't use.

A reading usually takes 50 to 300 ms. Controllers at the far end of a long bus segment can take over a second. When a controller does not answer at all (controller powered down, bus segment cut), the gateway keeps waiting for it for up to 60 seconds and then answers `504`.

Errors:

| Status | Meaning |
| --- | --- |
| 404 | No unit with that ID. |
| 500 | The controller reported a sensor fault. |
| 502 | The controller's answer was garbled on the bus. |
| 504 | The controller did not answer within 60 seconds. |

## Limits

Each client may have at most **16 requests in progress** at a time. A request that arrives while 16 requests from the same client are still in progress is answered `429 Too Many Requests` at once, and a client that keeps going over the limit is locked out for an hour.

A request counts against the limit until the gateway has sent its response, or until the client closes the connection.

## Our notes

- The plant-room gateway is `http://bms-gw.dc2.larchmont.example:8640`; from the office we point `COLDCTL_GATEWAY` at a tunnel.
- The gateway has no test instance. `tests/fakegateway.py` imitates the endpoints above for our tests.
