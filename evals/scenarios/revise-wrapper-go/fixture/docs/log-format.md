# Crossing logs

Each pier's ticket office keeps a crossing log: UTF-8 text, one scheduled sailing per line, four fields separated by tabs.

```
2026-09-14	Inchmara–Dunvoan	07:30	07:34
2026-09-14	Inchmara–Dunvoan	09:00	cancelled
```

| Field | Form |
| --- | --- |
| date | `YYYY-MM-DD`, a real date: the day of the scheduled departure |
| route | the route as the timetable names it (`Inchmara–Dunvoan`, with an en dash): not empty, no tab, no space at either end |
| scheduled | `HH:MM`, 00:00 to 23:59 |
| departed | `HH:MM` when the ferry left, or `cancelled` |

Blank lines and lines starting with `#` are ignored. Lines come in the order the office wrote them, which is usually, but not always, departure order; logs from several piers and weeks are often read together.

A sailing's delay is the minutes from its scheduled to its actual departure, negative when it left early. No sailing leaves more than 12 hours early or late, so a departure on the other side of midnight counts across it: scheduled 23:50 and departed 00:05 is 15 minutes late, scheduled 00:10 and departed 23:58 is 12 minutes early.

A log that breaks these rules is refused with its name and the line number: `ferry: logs/2026-09-14.log:7: bad departure "late" (want HH:MM or cancelled)`.
