# Check codes

Every pass carries a check code that the turnstiles verify offline, without asking any server: the turnstile controller holds the event's secret and recomputes the code from the pass ID on the ticket. The derivation is fixed by the turnstile firmware (4.x, "gatepass/v2"); anything that changes a single code means a reflash of every turnstile at the ground, which the facilities team schedules months ahead.

## Derivation

For pass `P-104233`, issue `0`, at event `EVT-2026-0412`:

1. Salt: `gatepass/v2:EVT-2026-0412:P-104233:0` (ASCII).
2. Key: PBKDF2 with HMAC-SHA256, the event's secret as the password, 300,000 iterations, 10 bytes of output.
3. Code: those 80 bits as 16 characters of Crockford base32 (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), most significant bits first, in groups of four: `M9FJ-7XD3-62MQ-W9NH`.

The work factor is deliberate. A turnstile verifies one code per entry, so it can afford it, but someone holding a list of pass IDs cannot cheaply guess codes.

## Issues

A pass that is reissued (a lost ticket, a transfer to another holder, an upgrade to another zone) gets the next issue number, and so a new code, which retires the old one: the turnstile file carries only each pass's latest issue, and the controller refuses any other. The box office's export has one row per issue, in the order they were made (docs/sales-export.md), so a pass's issue number is how many rows for it come before.

## The turnstile file

`gatepass build` writes the file the controllers load: a header, then one line per pass, in the order passes were first sold.

```
pass_id,zone,issue,code
P-104233,NORTH,0,M9FJ-7XD3-62MQ-W9NH
P-104234,EAST,2,RJPK-JKFP-YSG7-FEKR
```

The controller loads it as is and the print shop diffs it against the previous run for the same event, so the same export must always give the same file, byte for byte.
