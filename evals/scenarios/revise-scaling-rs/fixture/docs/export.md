# The booking export

Every night at 05:00 the city booking system exports every upcoming booking (today onwards, for all centres) as CSV with this header:

```
ref,facility,date,start,end,status,booked_by
```

- `ref`: the booking reference, given once when the booking is made (`B26-0004512`). The export lists bookings in reference order, which is the order they were made in, not the order of their dates.
- `facility`: the centre code and the facility (`KGS-SQ3`, `RVP-POOL-L4`, `ASH-ST2`). Online and app bookings always write the code in upper case; manual bookings at a desk are typed by staff, so the same court can appear as `kgs-sq3` or `KGS - SQ3`. Codes that agree ignoring case and spaces are the same facility.
- `date`: `YYYY-MM-DD`.
- `start`, `end`: `HH:MM`, 24-hour. A booking ends after it starts, on the same day.
- `status`: `confirmed`, `provisional` (held for a club or school until they confirm), or `cancelled` (kept in the export for a week after cancelling).
- `booked_by`: the member (`M004512`), club (`C0042`), or desk (`DESK-KGS`) that made it.
