# First-response SLA

Every ticket has a first-response target that depends on its priority and counts only the desk's business time. Support works out when the first response is due with `tools/sla_due.pl`, and the weekly breach report runs it over the week's tickets.

## The calendar

The files live in the config directory (`config/` in this repository, and in the image).

`business-hours.conf` gives the desk's opening hours in the office's local time, one span per line: a day (`mon` to `sun`) and `HH:MM-HH:MM`. A day can have several spans (the lunch break is the gap between two); days that are not listed are closed. `24:00` may end a span.

```
mon 08:30-12:30
mon 13:30-17:30
sat 10:00-13:00
```

`holidays.txt` lists dates whose hours differ from their weekday's: a date alone is closed all day, and a date with one or more spans (one per line) is open only for those spans, whatever its weekday.

```
2026-12-25
2026-12-24 08:30-12:30
```

`sla-targets.conf` gives each priority's target in business time, as hours (`4h`) or minutes (`90m`).

```
P1 1h
P2 4h
```

Spans of one day may not overlap or touch, and `#` starts a comment in all three files.

## When a response is due

Start from the time the ticket was opened, to the minute (seconds are dropped). Count the target's minutes through the open spans from that moment on, day after day: time outside the spans (nights, lunch, closed days, holidays) does not count, and a ticket opened outside the spans starts counting when the next span opens. The response is due at the minute the count runs out. When it runs out exactly as a span closes, it is due at that closing time, not at the next opening; a span ending at `24:00` makes that midnight, shown as `00:00` of the next day.

Times are the office's local time as the ticketing system exports them (`2026-10-02T16:45`, or with seconds), and due times are written the same way, to the minute.

A priority with no target has no due time.

## Examples (with the repository's calendar)

| Opened | Priority | Due |
| --- | --- | --- |
| Thu 2026-10-01 12:45 | P1 | 2026-10-01T14:30 (opened over lunch) |
| Thu 2026-10-01 07:10 | P2 | 2026-10-01T12:30 (the morning span's closing time) |
| Fri 2026-10-02 16:45 | P2 | 2026-10-06T09:30 (Saturday morning; Monday the 5th is a holiday) |
| Wed 2026-12-23 17:00 | P2 | 2026-12-24T12:00 (Christmas Eve is open in the morning only) |
