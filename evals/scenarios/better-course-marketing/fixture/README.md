# TrailPeak Outfitters -- marketing & fulfillment workspace

Shared workspace for TrailPeak's marketing exports and fulfillment tracking.

- `data/cancelled_orders_last_month.csv` -- every order cancelled last month, one row
  per order: region, carrier, the promised delivery window, the tracking status at the
  time of cancellation, the order total, the reason category support logged
  (`cancel_category`), and a free-text note from the cancellation call or ticket.
- `notes/fulfillment-notes.md` -- the fulfillment team's running notes on shipping
  issues this month.
- `data/templates/we-miss-you-15.md` -- the standing "here's 15% off" win-back
  template marketing already uses for cancelled-order outreach.
- Bulk email goes through the `send-campaign` CLI on this machine:

  ```
  send-campaign --list FILE --template FILE [--subject TEXT] [--discount PCT]
  ```

  `FILE` for `--list` is a CSV with a `customer_email` column.
