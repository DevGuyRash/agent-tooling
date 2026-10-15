# JSON export

The data team wants the weekly report as JSON for their dashboard:

```
python3 -m stallbook --data data report --week 2026-W14 --format json
```

The output is one JSON object:

```
{
  "week": "2026-W14",
  "lines": [
    {"item": "Sourdough loaf", "category": "bread", "units": 15, "revenue": "68.40"},
    {"item": "Honey", "category": "preserves", "units": 5, "revenue": "45.00"}
  ],
  "total_units": 20,
  "total_revenue": "113.40"
}
```

- `lines` has one object per item, in the same order as the text report. A week with no sales has an empty list and totals of `0` and `"0.00"`.
- `units` and `total_units` are numbers.
- `revenue` and `total_revenue` are strings with two decimals and a `.`, so the dashboard never sees a float.
