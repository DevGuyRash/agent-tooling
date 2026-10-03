# The roster file

The coordinators keep the roster as a UTF-8 CSV with this header and one line per shift:

```
date,start,end,station,volunteer
2026-09-14,09:00,12:00,Prep,Amara Okafor
```

- `date` is `YYYY-MM-DD`; `start` and `end` are 24-hour `HH:MM`, and a shift ends after it starts, on the same day.
- `station` is where in the kitchen (Prep, Serving, Dish pit, Delivery, Front desk, ...); `volunteer` is the name as the volunteer writes it, in any script.
- Cells are trimmed; blank lines are skipped. Lines need not be in date order.

A line that breaks these rules stops every command with `shiftboard: FILE:LINE: problem` on standard error and exit status 1.
