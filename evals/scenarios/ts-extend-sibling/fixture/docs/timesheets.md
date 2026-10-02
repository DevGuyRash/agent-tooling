# Timesheets

Everyone keeps one file per month in `timesheets/`, named `YYYY-MM-NAME.txt`:

    # Dana, September 2026
    2026-09-01  09:00-10:30  acme/site   homepage review
    2026-09-01  1h15         acme/brand  logo variants
    2026-09-02  45m          bolt/app    standup

Each line is one entry: DATE, TIME, PROJECT, and an optional NOTE, separated by spaces or tabs.

- DATE: `YYYY-MM-DD`, a date that exists.
- TIME: either a range `HH:MM-HH:MM` on a 24-hour clock (`00:00` to `23:59`), ending after it starts, or a duration: `2h`, `1h15` (the minutes as two digits, under 60), or `45m`. Either way it must come to more than zero minutes.
- PROJECT: `CLIENT/PROJECT`, each part made of lowercase letters, digits, and hyphens. CLIENT is the id the client has in the rate card (`rates.txt`, see [rates.md](rates.md)); `studio/...` is our own time.
- NOTE: the rest of the line, free text.

Blank lines and lines starting with `#` (after any spaces or tabs) are ignored. Any other line is an error, reported as `FILE:LINE: message`.
