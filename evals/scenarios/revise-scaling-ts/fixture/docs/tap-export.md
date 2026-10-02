# The tap export

Every night the back office exports the service day's taps (04:00 to 03:59 the next morning) as CSV with this header:

```
ts,card,route,stop,fare_cents,batch
```

- `ts`: the reader's local time, `YYYY-MM-DDTHH:MM:SS`.
- `card`: the contactless card's twelve-digit number. Readers on firmware 3.x print it in groups of four (`4402 7713 0981`); everything else prints the twelve digits.
- `route`: the route the bus was running (`12`, `X3`, `N1`).
- `stop`: the stop code (`KV1042`).
- `fare_cents`: the single-journey fare the reader worked out for this boarding, in cents. Firmware 3.x pads it to four digits (`0240`).
- `batch`: the upload batch the tap arrived in (`R0193-0451` is reader 0193's 451st upload; `BO-…` batches are re-sends from the back office).

Lines are in the order the back office received them, which is not time order: a bus out of signal uploads when it gets coverage back, sometimes hours later. A reader that loses its connection mid-upload sends the whole batch again, and the back office re-sends taps it was unsure about (in the plain twelve-digit format, whatever reader they came from), so the same tap can appear more than once.
