# CSV export

Finance wants the weekly report as CSV for their spreadsheet:

```
python3 -m stallbook --data data report --week 2026-W14 --format csv
```

The columns, in this order:

| column     | value                                                                                   |
| ---------- | --------------------------------------------------------------------------------------- |
| `item`     | the item name, as in the text report                                                    |
| `category` | the item's category                                                                     |
| `units`    | units sold that week, a whole number                                                    |
| `revenue`  | revenue for the week with two decimals and a `.`, no currency symbol, no thousands separator (`1234.50`) |

- The first line is a header with the column names.
- Then one line per item, in the same order as the text report.
- There is no totals line.
- A week with no sales prints the header and nothing else.
- Names and categories that contain a comma, a double quote or a line break are quoted the usual CSV way.

Example:

```
item,category,units,revenue
Sourdough loaf,bread,15,68.40
Honey,preserves,5,45.00
Rye roll,bread,30,36.00
"Jam, plum",preserves,7,31.50
```
