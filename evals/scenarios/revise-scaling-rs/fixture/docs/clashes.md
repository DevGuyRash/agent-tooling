# The morning clash list

`bookdesk clashes EXPORT.csv` prints every pair of bookings that clash, for the front desks to sort out before opening.

Two bookings clash when they are for the same facility (see [export.md](export.md)) on the same date, neither is cancelled, and their times overlap: each starts before the other ends. Back-to-back bookings (one ends at 19:00, the next starts at 19:00) do not clash.

Each pair is listed once, ordered by where its first booking is in the export, then where its second is: the desks work down the list in that order. A line gives the facility code in its usual form, the date, and then each booking's reference, times, who booked it, and `(provisional)` if it is only held:

```
KGS-SQ3  2026-09-19  B26-0004512 18:20-19:00 M004512  B26-0009931 18:40-19:20 DESK-KGS (provisional)
```

The last line counts them (`3 clashes on 2 facilities`), or says `no clashes`.
