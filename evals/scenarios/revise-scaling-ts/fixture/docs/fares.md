# Fare rules

These are the rules the nightly charge run applies to one service day's taps (see [tap-export.md](tap-export.md)). Taps are taken in the export's order.

1. **Duplicates.** A tap whose time, card, route, stop and fare match an earlier line is the same tap uploaded again and is dropped. Which batch it came in does not matter.
2. **Transfers.** A tap up to 60 minutes after the start of the card's current journey is a transfer and costs nothing. The current journey started at the card's last tap (in the export's order) that was not itself a transfer. A tap timed before that start is not a transfer.
3. **Fares and the daily cap.** Any other tap starts a journey and is charged its fare, but a card is never charged more than its daily cap in a service day: €7.20, or €3.60 for concession cards (card numbers starting with 9). The tap that reaches the cap is charged what is left; later journeys that day cost nothing (they are still journeys, and transfers count from them).

## What the run writes

`tapfare charge TAPS.csv --out DIR` checks every line first; if any line is bad it lists them and writes nothing (exit 1). Otherwise it writes two files to `DIR`:

- `charges.csv`: `ts,card,route,stop,fare_cents,charged_cents,reason`, one line per tap kept, in the export's order. `reason` is `fare` (charged the full fare), `transfer`, or `capped` (charged less than the fare because of the cap). Cards are written as twelve digits and fares without padding.
- `debits.csv`: `card,taps,charged_cents`, one line per card, in the order cards first appear in `charges.csv`. Billing debits each card's account with `charged_cents` the next morning.

and prints one summary line: taps charged, cards, duplicates dropped, the day's fares, and how many cards reached their cap.
