# Overdue fines

Approved by the library board on 12 February 2025. This is the policy the circulation desk charges.

## How much

| Category | What it covers | Per day late | Most one item can owe |
| --- | --- | --- | --- |
| `adult` | adult books, audiobooks, magazines | 0.30 | 7.00 |
| `children` | children's and teen books | 0.15 | 2.50 |
| `media` | DVDs, Blu-rays, video games | 1.25 | 10.00 |

The category is the `category` column of the loans export (docs/export-format.md).

## Days late and the grace period

An item is as many days late as there are calendar days from its due date to the day it came back. An item back on or before its due date is not late.

An item 3 days late or less owes nothing: that is the grace period. From the fourth day late every day counts, the first three included: a children's book back 5 days late owes 5 × 0.15 = 0.75.

An item never owes more than the most for its category: a DVD back 12 days late owes 10.00, not 15.00.
