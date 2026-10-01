---
name: ledgerline-import
description: Convert expense notes or receipts into a Ledgerline import file (.ll), the line format a finance team loads into its ledger. Use when asked to prepare, convert, or check a Ledgerline import.
---

# Ledgerline Import

A Ledgerline import file is plain text with one record per line:

1. The first line is exactly `LLv3`.
2. Each expense is one line `LL|<date>|<amount>|<category>|<memo>`:
   - `<date>` is `YYYY-MM-DD`, taking the year from the notes' heading.
   - `<amount>` is the amount in cents as a whole number, with no currency sign or separators (`42.50` becomes `4250`).
   - `<category>` is `TRV` for travel, `MEA` for meals, `SUP` for supplies, and `OTH` for anything else.
   - `<memo>` is the expense's own description, without the date or amount.
3. The last line is `END|<number of expense lines>`.

Keep the expenses in the order the notes list them, and check the `END` count before saving.
