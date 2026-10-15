# Notices

A notice is a small JSON object sent to one device with `transport.send(device_id, payload)`.

## Delivery

Delivery is best-effort. `send` hands the notice to the push gateway client, which already retries with backoff when the gateway or the device is unavailable, and drops a notice it still cannot deliver. `send` raises `TransportError` for a device the gateway does not know, and that is final.

A notice that cannot be sent never undoes or blocks the change it reports, and one device failing never stops the notices to the user's other devices.

## Critical notices

`password_changed` is an account-security notice. Critical notices are signed with the service key so that a device can tell them from forgeries, written to the audit log, and tracked in the receipt store until the device acknowledges them. `notices.send_critical` does all of that.

```
{"type": "password_changed", "user_id": "u1", "notice_id": "n7", "signature": "9f2c..."}
```

## Informational notices

Everything else is informational.

### display_name_changed

Sent to every device of the user, once per change, after the display name has changed. Setting the name it already has changes nothing and sends nothing.

```
{"type": "display_name_changed", "user_id": "u1", "display_name": "Ada L.", "previous": "Ada"}
```

`display_name` is the new name and `previous` the one it replaces.
