# The week board

The kiosk by the kitchen door shows a week's shifts so volunteers can find their slot without logging in to anything. `shiftboard week ROSTER WEEK` prints that board:

```
python3 -m shiftboard week roster.csv 2026-W38
```

## The week

WEEK is an ISO 8601 week written `YYYY-Www`, as in `2026-W38`. Weeks run Monday to Sunday, and week 1 of a year is the week holding its first Thursday, so `2026-W01` starts on Monday 29 December 2025 and some years have a week 53. Anything else, or a week the year does not have, is an error: `shiftboard: bad week 'WEEK'` on standard error and exit status 2, checked before the roster is read.

## The board

One row per shift dated in that week, in date and start-time order; shifts with the same date and start keep their roster order. Four columns:

| Column | Holds |
|---|---|
| Day | weekday abbreviation and day of month, as `Mon 14` (no leading zero: `Thu 1`) |
| Time | start and end, as `09:00-12:30` |
| Volunteer | as in the roster |
| Station | as in the roster |

The first line holds the column names, the second a rule of `-` under each column, then the rows. Every column is as wide as its widest entry, column name included; entries are left-aligned and padded with spaces to that width, columns are two spaces apart, and no line ends in a space.

Widths are counted the way the kiosk's terminal shows text: a character that Unicode's East Asian Width property classes as Wide (W) or Fullwidth (F), which covers Chinese, Japanese, and Korean characters and the fullwidth forms, takes two columns, and every other character takes one. Several volunteers write their names in Chinese or Korean, and the board has to line up for them as well.

A week with no shifts prints `No shifts in WEEK.` (the week as given) and exits 0. Roster errors are reported as `shiftboard check` reports them.

Other code gets the same board from `shiftboard.board.render_week(shifts, week)`, given the shifts as `shiftboard.roster.load` returns them and the week as written above. It returns the board's lines joined with newlines, without a final newline, and raises `ValueError` for a bad week.

## Example

For `docs/examples/roster-sample.csv` and week `2026-W38`, `shiftboard week` prints the board below; `docs/examples/week-2026-W38.txt` holds exactly what it prints.

```
Day     Time         Volunteer        Station
------  -----------  ---------------  ----------
Mon 14  09:00-12:00  Amara Okafor     Prep
Mon 14  09:00-12:00  张伟             Serving
Mon 14  12:00-15:00  Tomasz Nowak     Dish pit
Wed 16  17:00-20:00  김민준           Serving
Wed 16  17:00-20:00  Lucía Fernández  Prep
Fri 18  10:00-13:30  陈美玲           Delivery
Sat 19  09:00-12:00  Amara Okafor     Front desk
Sun 20  11:00-14:00  王芳             Serving
```
