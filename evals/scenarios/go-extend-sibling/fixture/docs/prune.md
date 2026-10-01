# bakctl prune (#41)

`bakctl prune` plans which snapshots a retention policy keeps and which it drops. It only prints the plan: it deletes nothing and contacts nothing.

```
bakctl prune [options] CATALOG
```

CATALOG is a catalog file in the format `bakctl list` reads, or `-` for standard input. Options come before CATALOG and can be written `--keep-daily 7` or `--keep-daily=7`.

## Options

| Option | Meaning |
| --- | --- |
| `--keep-last N` | keep the N newest snapshots |
| `--keep-hourly N` | keep the newest snapshot of each of the N most recent hours that have one |
| `--keep-daily N` | the same for days |
| `--keep-weekly N` | the same for ISO 8601 weeks |
| `--keep-monthly N` | the same for calendar months |
| `--keep-yearly N` | the same for calendar years |
| `--keep-within DURATION` | keep every snapshot created within DURATION of the newest one |
| `--host HOST` | plan only the series of this host |
| `--set SET` | plan only the series of this set |
| `--ids` | print only the ids of the snapshots to drop |

N is a whole number written in digits; `0` turns the rule off. DURATION is one or more parts `<digits>w`, `<digits>d`, `<digits>h`, in that order and each at most once: `36h`, `2w`, `1w3d`, `10d12h`. A day is 24 hours and a week 7 days; a duration of zero turns the rule off.

At least one keep rule (the seven `--keep-` options) must be on. Without one, prune refuses, so that a mistyped policy can never plan to drop everything.

## Which snapshots are kept

Each series (the snapshots with the same host and set) is planned on its own. Within a series, snapshots are ordered newest first by created time; snapshots created in the same second are ordered by id, the smaller id (byte order) first, and the rules treat that order as newest first.

The keep rules look only at snapshots in state `ok`:

- `last`: the first N ok snapshots in that order.
- `hourly`, `daily`, `weekly`, `monthly`, `yearly`: walk the ok snapshots in that order and keep each one whose period differs from the period of the ok snapshot before it (the first one always differs), until the rule has kept N. Periods are in UTC: convert the created time to UTC first. An hour is a date and hour, a day a date, a week an ISO 8601 week (Monday to Sunday, numbered within its ISO week-numbering year, so Monday 2025-12-29 is in week 1 of 2026), a month a year and month, a year a year.
- `within`: every ok snapshot created at or after the newest ok snapshot's created time minus DURATION. A series with no ok snapshot keeps nothing by this rule.

The rules are independent: each one walks the whole series, and a snapshot is kept when any rule keeps it.

Apart from the rules:

- A snapshot tagged `pinned` is always kept, whatever its state. When it is ok it also counts in the rules like any other.
- A `partial` snapshot created after the newest ok snapshot of its series, or in a series with no ok snapshot, is an upload still in progress and is kept.
- Every other partial snapshot, and every failed one, is dropped.

Each kept snapshot lists every reason it is kept, in this order: `pinned`, `in-progress`, `last`, `within`, `hourly`, `daily`, `weekly`, `monthly`, `yearly`. A dropped snapshot has exactly one reason: `failed`, `partial`, or `expired` (an ok snapshot no rule keeps).

## Output

The series in order of host, then set (byte order), separated by blank lines. Each series is a header line followed by one line per snapshot, in the order above:

```
HOST/SET: keep K, drop D
  ACTION  ID  CREATED  REASONS
```

ACTION is `keep` or `drop`; CREATED is the created time in UTC, printed the way `bakctl list` prints it (`2026-01-05T02:00:00Z`); REASONS is the reasons joined with commas. Snapshot lines start with two spaces and their fields are separated by two spaces. After the last series come a blank line and the total:

```
total: keep K, drop D, frees SIZE
```

SIZE is the sum of the dropped snapshots' bytes, formatted the way `bakctl usage` formats sizes. When there is no series to plan (an empty catalog, or `--host` or `--set` matching nothing), the output is the total line alone.

With `--ids`, the output is only the ids of the dropped snapshots, one per line, in the same order as above, and nothing at all when nothing is dropped.

## Exit status

- 0: the plan was printed.
- 1: the catalog cannot be read or is invalid. The error goes to standard error the way `bakctl list` reports it, and nothing goes to standard output.
- 2: usage error (an unknown option, a bad number or duration, no keep rule, no CATALOG or more than one). A message goes to standard error and nothing to standard output.

## Example

With [prune-example.tsv](prune-example.tsv):

```
$ bakctl prune --keep-last 2 --keep-daily 3 --keep-weekly 2 docs/prune-example.tsv
db-1/pgdump: keep 5, drop 5
  keep  s-0e1f0a  2026-01-07T02:00:03Z  in-progress
  keep  s-0e1f09  2026-01-06T02:41:57Z  last,daily,weekly
  drop  s-0e1f08  2026-01-06T02:00:01Z  failed
  keep  s-0e1f07  2026-01-05T14:12:09Z  last,daily
  drop  s-0e1f06  2026-01-05T02:00:05Z  expired
  keep  s-0e1f05  2026-01-04T02:00:03Z  daily,weekly
  drop  s-0e1f04  2026-01-03T03:10:40Z  expired
  drop  s-0e1f03  2026-01-03T02:00:02Z  partial
  drop  s-0e1f02  2026-01-02T02:00:04Z  expired
  keep  s-0d77a1  2025-12-15T02:00:02Z  pinned

web-1/etc: keep 3, drop 1
  keep  s-1c3304  2026-01-05T03:10:00Z  last,daily,weekly
  keep  s-1c3303  2026-01-04T03:10:00Z  last,daily,weekly
  keep  s-1c3302  2025-12-30T03:10:00Z  daily
  drop  s-1c3301  2025-12-28T03:10:00Z  expired

total: keep 8, drop 6, frees 6.7 GiB
```

The nightly job keeps running as it does today.
