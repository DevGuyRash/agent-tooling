# stampcard specification

stampcard reads a day's sales events from the till and the shop's loyalty cards, credits stamps, works out the free drinks that were earned, and prints a report. This file is the requirement. Each numbered line is one requirement; the numbers are stable.

## Scope

- **R1.** stampcard runs once a day on the shop's back-office computer. The events file is written to local disk by the till software and the cards file by the owner, and both are trusted: hostile input and authentication are out of scope. The till can send the same event twice, though (see R3). A run handles at most 2,000 events against at most 300 cards.

## Input

- **R2.** The events file holds one JSON object per line with the fields `id` (string), `card` (string), `kind` (`"purchase"` or `"refund"`), `cents` (integer greater than 0) and `ts` (string). Blank lines are ignored. Any other line (not JSON, not an object, a field missing or of the wrong type, an unknown `kind`, `cents` not a positive integer) is rejected with the reason `malformed`.
- **R3.** Valid events are applied in file order, each exactly as written. An event whose `id` was already applied earlier in the same run is a replay: it is rejected with the reason `replay` and changes nothing.
- **R4.** The cards file is a CSV with the header `id,name,stamps`. `stamps` is the card's balance at the start of the run, from 0 to 9. A card is looked up in the file when an event first names it: `Directory` asks its lookup function about a card id at most once per run, whether or not the card exists, and remembers the answer.

## Stamps

- **R5.** A purchase earns one stamp for every full 4.00 spent (`cents // 400`), at most 3 stamps per purchase.
- **R6.** When a card reaches 10 stamps it earns one free drink and 10 stamps are taken off its balance. Stamps beyond 10 stay on the card: a card with 8 stamps that earns 3 more has 1 stamp left and one free drink.
- **R7.** A refund takes off the stamps a purchase of the same amount would have earned (R5), but a card's stamps never go below 0. A refund is always applied, even when the card has fewer stamps than it takes off; it then leaves the card at 0. Free drinks already earned stay earned.
- **R8.** An event for a card that is not in the cards file is rejected with the reason `unknown-card`, and the run goes on with the next line.

## Notifications

- **R9.** When an event earns a free drink, the customer is told through the transport, a function that takes one message, a dict with `to` (the card id), `name` and `text`. If the transport raises, the notification is retried up to 3 more times, after waits of 1, 2 and 4 seconds (4 attempts in all). The waits are made by a `sleep` function the caller can pass, `time.sleep` by default. If the last attempt fails too, the failure is written to standard error and counted as `notify failed`, and the run goes on. A notification failure never changes a balance or the exit status.

## Report

- **R10.** The report is plain text on standard output. Reports come from named formats: `text`, the layout below, is built in, and `register_format(name, fn)` adds a format whose `fn(summary)` returns the report text (registering a name again replaces it). In the text layout, `events` counts the lines that are not blank; `rejected` lists the reasons in alphabetical order as `reason: count`, in parentheses, and has no parentheses when nothing was rejected; `cards` lists, sorted by id, every card an applied event touched.

```
stampcard report
events: 3
applied: 2
rejected: 1 (malformed: 1)
free drinks: 0
notify failed: 0
cards:
  C-001  stamps 9  drinks 0
  C-004  stamps 1  drinks 0
```

That is the report for the cards file `C-001,Ada,8` and `C-004,Di,0` and an events file with a 4.50 purchase on each card and one line that is not an event.

## Interfaces

- **R11.** `python3 -m stampcard EVENTS CARDS [--outbox FILE] [--format NAME]` runs the program. The report, in the format NAME (default `text`), goes to standard output, and each notification message goes to FILE (default `outbox.jsonl`) as one JSON object per line. The exit status is 0 when the run finishes, even if events were rejected, and 2 when a file cannot be read, the arguments are wrong, or NAME is not a registered format.
- **R12.** The library interface is `stampcard.batch.run(lines, directory, transport, sleep=time.sleep)`, which returns the run's `Summary`; `stampcard.report.render(summary, fmt="text")`, which returns the report in the named format and raises `ValueError("unknown format: NAME")` for a name nobody registered, and `stampcard.report.register_format(name, fn)`; `stampcard.directory.Directory(lookup)`, where `lookup(card_id)` returns a `Card(id, name, stamps)` or `None`, and whose `get(card_id)` returns the `Card` or raises `KeyError`; and `stampcard.notify.notify_reward(card, transport, sleep=time.sleep)`, which sends one notification, with the retries of R9, and returns whether the transport took it.
