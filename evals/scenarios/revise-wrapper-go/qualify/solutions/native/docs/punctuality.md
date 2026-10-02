# Punctuality figures

`ferry punctuality [--from DATE] [--to DATE] LOG...` prints one line per route for the harbour board's weekly sheet, which reads it as it is. `--from` and `--to` keep the sailings dated in that range, both ends included; either may be left out.

```
$ ferry punctuality --from 2026-09-14 --to 2026-09-14 logs/*.log
route                sailings  cancelled  on time  median  worst  by 5 minutes
Eilean Rùm–Kilbride         2          0        1     7.5     15  0:1 15:1
Inchmara–Saltness           4          0        2       6     21  -5:1 5:2 20:1
Kilbride–Eilean Rùm         2          0        1      27     54  0:1 50:1
Dunvoan–Inchmara            6          0        4       4     22  0:4 5:1 20:1
Inchmara–Dunvoan            6          0        4     4.5     21  -5:1 0:2 5:1 20:2
Dunvoan–Kilbride            3          0        3       4      5  0:2 5:1
Kilbride–Dunvoan            3          0        3       1      3  0:3
Saltness–Inchmara           4          0        4       2      4  -5:1 0:3

30 sailings, 0 cancelled, 22 of 30 on time
```

## Figures

| Column | What it is |
| --- | --- |
| `route` | the route |
| `sailings` | its scheduled sailings in the range |
| `cancelled` | those cancelled |
| `on time` | sailings that ran and left at most 5 minutes late; an early departure is on time |
| `median` | the middle delay of the sailings that ran, in minutes; with an even number of them, halfway between the middle two (`2.5`); `-` when none ran |
| `worst` | the longest delay, in minutes (negative if every sailing that ran left early); `-` when none ran |
| `by 5 minutes` | the sailings that ran, counted in five-minute bands of delay, earliest band first, each written `START:COUNT`: band `0` is 0 to 4 minutes late, `5` is 5 to 9, `-5` is 1 to 5 minutes early, `-10` is 6 to 10 early, and so on; bands with no sailings are left out, and it is `-` when none ran |

Routes are listed least punctual first, by the share of the sailings that ran which were on time; a route where nothing ran comes before every other. Routes with the same share keep the order in which they first appear in the logs (logs in the order given).

## Layout

Columns are two spaces apart and as wide as their widest cell, header included, counted in characters; `route` is padded on the right, the numbers on the left, and the bands come last, unpadded. After a blank line, the totals: `N sailings, C cancelled, O of R on time`, where R is the sailings that ran. When the range holds no sailings the output is the single line `no sailings`.
