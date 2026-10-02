# fxd: the store machines' exchange-rate daemon

Every store machine (back office PCs, the label printers' hosts, the tills) runs fxd. Finance's morning job loads the day's rates into it; anything on the machine can ask it for one.

## Where

A Unix socket at `/run/fxd/fxd.sock`. The `FXD_SOCKET` environment variable, when set, names the socket instead (test rigs and the printers' staging host use it).

## Protocol

One request per connection: send one line, read one line. fxd closes the connection after its reply.

```
RATE <from> <to>\n
```

for example `RATE CHF EUR\n`. The reply is one of:

```
OK <rate> <date>\n       one <from> is worth <rate> <to>; <rate> is a decimal with up to six places, <date> the day it is for
ERR <reason>\n           no rate for that pair today, or a request fxd did not understand
```

```
$ printf 'RATE CHF EUR\n' | socat - UNIX-CONNECT:/run/fxd/fxd.sock
OK 0.9615 2026-10-01
```

fxd answers in well under a millisecond; a client has no reason to wait longer than a second. When fxd is not running, the socket is missing, or it is still there from before a crash and refuses connections.

## Converting prices

Rates are decimals: convert with `decimal.Decimal`, never floats. A converted price is the price times the rate, rounded to the cent, halves up.
