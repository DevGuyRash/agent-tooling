# The library system's nightly exports

At 01:30 the library system writes two files to `/srv/ils-export/` on the circulation box: `loans.csv` and `patrons.csv`. Both are comma-separated UTF-8 with a byte-order mark and a header row; columns may come in any order, and values may have spaces around them.

## loans.csv

One row per loan still out, and per returned loan whose fine has not been paid yet.

| Column | Meaning |
| --- | --- |
| `loan_id` | `L-` and a number |
| `patron_id` | `P-` and a number |
| `barcode` | the item's barcode |
| `title` | the item's title |
| `category` | the item's fine category (docs/fines.md); the system writes it in whatever case the cataloguer typed |
| `due` | due date, `YYYY-MM-DD` |
| `returned` | the day it came back, `YYYY-MM-DD`; empty while the item is out |

## patrons.csv

| Column | Meaning |
| --- | --- |
| `patron_id` | `P-` and a number |
| `name` | the name on the card |
