# How an invoice adds up

Amounts are pounds, held as decimals and rounded half up to the penny (0.125 becomes 0.13).

- A line's net is its quantity times its unit price, rounded to the penny.
- A line's VAT is its net times its VAT rate, rounded to the penny. Each line is rounded on its own; this is the VAT amount printed on the line.
- The VAT summary under the lines has one row per rate, highest rate first, holding the sum of those lines' nets and the sum of those lines' VAT amounts.
- The invoice's net, VAT, and total are the sums of the summary rows, and so the sums of the printed lines.

Every figure on a printed invoice is the sum of figures printed above it, so a customer who adds up the lines gets the totals. Before 2.3.0, VAT was rounded once on each rate's net, and some customers' totals came out a penny away from the lines they could see (#31).
