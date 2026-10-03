# How an invoice adds up

Amounts are pounds, held as decimals and rounded half up to the penny (0.125 becomes 0.13).

- A line's net is its quantity times its unit price, rounded to the penny.
- Each line shows its own VAT, its net times its VAT rate, rounded to the penny.
- The VAT summary under the lines has one row per rate, highest rate first: the rate's net, and VAT on that net, rounded to the penny.
- The invoice's net, VAT, and total are the sums of the summary rows.
