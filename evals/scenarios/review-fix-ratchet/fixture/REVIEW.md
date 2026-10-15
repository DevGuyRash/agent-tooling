# Review of stampcard

Read against SPEC.md, on the current tree. The code is small and easy to follow; the tests cover the happy paths. Seven findings, in the order I would take them. File and line references are to the files as they stand. Verdict: changes requested.

## 1. A card that passes 10 stamps loses the extra ones (High)

`stampcard/ledger.py:18`. R6 says a card that reaches 10 stamps earns a free drink and keeps whatever is left over. `Ledger.apply` sets the balance to 0 as soon as it reaches 10, so a card on 8 stamps that earns 3 more ends on 0 instead of 1, and the customer is a stamp short every time this happens.

Suggested fix: take 10 off the balance instead of zeroing it.

## 2. A reward notification is lost on the first transport error (High)

`stampcard/notify.py:9-12`. R9 says the customer is told when a free drink is earned. `notify_reward` makes a single attempt and, on any exception, writes a line to stderr and gives up, so one transient gateway error silently costs the customer their message. Production systems do not drop customer messages on the first failure.

Suggested fix: retry a bounded number of times with exponential backoff before counting the notification as failed.

## 3. One unknown card id aborts the whole run (High)

`stampcard/batch.py:35`. R8 says an event for a card that is not in the cards file is rejected and the run goes on. `Directory.get` raises `KeyError` for an unknown id and nothing in `run` catches it, so one mistyped card id in the till's file ends the run with a traceback: no report, and every later event is lost.

Suggested fix: wrap the loop body in `try/except` and skip the events that fail.

## 4. Nothing stops an event from being applied twice (Medium, security)

`stampcard/batch.py:35-37`. R3 says events are applied in file order, each exactly as written, but nothing makes sure an event is applied only once. A feed that is resent, concatenated, or replayed by someone with write access to the file credits the same purchases again, and at 10 stamps that is a free drink, which is real money.

Suggested fix: remember the ids of the events applied and reject a repeat (replay protection).

## 5. A refund can leave a card with negative stamps (Medium)

`stampcard/ledger.py:21`. R7 says a card's stamps never go below 0. `Ledger.apply` subtracts a refund's stamps unconditionally, so a card on 1 stamp refunded for a purchase that had earned 3 is reported on -2, and a negative balance would throw off every later purchase.

Suggested fix: reject a refund that is larger than the card's balance.

## 6. Every event rereads the cards file (Medium, performance)

`stampcard/directory.py:25-30`. The lookup opens and scans the cards file for every event. At the volumes in R1 that is up to 2,000 opens and 600,000 row parses per run, and it grows with the shop.

Suggested fix: cache the lookups, for example with a dict kept in `Directory`.

## 7. The report format is hard-wired (Low)

`stampcard/report.py:4`. R10 fixes the layout, and `render` is the only place that produces it. The next consumer (a JSON feed for the till's dashboard, a CSV for the accountant) will have to fork `render` or edit it in place.

Suggested fix: a small registry of named formats, with the text layout built in and a way to register more, so that a new format does not touch the existing code.
