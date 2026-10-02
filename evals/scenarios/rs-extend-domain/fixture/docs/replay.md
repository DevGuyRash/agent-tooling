# pagerlog replay

Requested by Priya Raman for the quarterly routing review. Before a routing change goes out, I want to see what it would have done with last quarter's alerts: send every alert in a history export through a routing file, at the time it fired, and compare where each alert went with where it would go now.

## Usage

```
pagerlog replay --routes FILE HISTORY
```

`--routes` is required, and may come before or after `HISTORY`, once.

## Where each alert would go

Each alert in `HISTORY` goes through the routing file `FILE`, and the files it includes, as [docs/routing.md](routing.md) describes: with the alert's labels, plus an `alertname` label holding its alert name, at the time it fired.

An alert has changed when the set of receivers it would go to is not the set it went to (the `receivers` field of the export); the order does not matter.

## Output

```
Replay of N alerts (FIRST to LAST) through FILE

RECEIVER TABLE

Changed: K of N alerts

CHANGE TABLE
```

- The first line: `N` is the number of alerts in `HISTORY`, `FIRST` and `LAST` the dates (`YYYY-MM-DD`) of the earliest and the latest, and `FILE` the routing file as given on the command line.
- The receiver table has a row for every receiver that at least one alert went to or would go to, ordered by name, with the columns `Receiver`, `Before` (alerts that went to it), `After` (alerts that would go to it), and `Change`: `After` minus `Before`, written as `+3`, `-3`, or `0`.
- `K` is the number of alerts that changed.
- The change table comes only when `K` is not 0; otherwise the output ends with the `Changed` line. It groups the changed alerts by alert name, receivers before, and receivers after, one row per group, with the columns `Alerts` (how many alerts are in the group), `Alert`, `Before`, and `After`. Receivers are written in name order, separated by `, `. Rows are ordered by `Alerts`, larger first, then by `Alert`, `Before`, and `After`.
- Text is ordered by character code, character by character, so `db-oncall` comes before `dba-oncall`; `Before` and `After` are ordered by their text as written.

The tables are laid out the way `pagerlog receivers` lays out its table: columns separated by two spaces, each as wide as its widest entry (header included, counting characters), text columns (`Receiver`, `Alert`, `Before` and `After` in the change table) left-aligned and number columns right-aligned, headers aligned like their column, and no spaces at the end of a line.

`pagerlog replay --routes routing/main.routes history/2026-q3.tsv` prints:

```
Replay of 240 alerts (2026-07-01 to 2026-09-30) through routing/main.routes

Receiver          Before  After  Change
blackhole              0     11     +11
dba-oncall             0     43     +43
ops-pager              3      0      -3
payments-oncall       46     35     -11
payments-tickets      52     79     +27
platform-oncall       76     46     -30
platform-tickets      10     10       0
platform-weekend      12      7      -5
search-oncall          0     18     +18
storage-oncall        53     48      -5
storage-tickets        0      5      +5

Changed: 120 of 240 alerts

Alerts  Alert             Before                             After
    15  ApiLatency        payments-oncall                    payments-tickets
    15  IndexBehind       platform-oncall                    search-oncall
    14  ApiLatency        payments-oncall                    payments-oncall, payments-tickets
    14  DiskFull          storage-oncall                     dba-oncall, storage-oncall
    11  BackupFailed      storage-oncall                     dba-oncall, storage-oncall
     8  ReplicationLag    payments-tickets                   dba-oncall, payments-tickets
     6  LoadGenSaturated  platform-oncall                    blackhole
     5  DiskFull          storage-oncall                     storage-tickets
     5  ReplicationLag    storage-oncall                     dba-oncall, storage-oncall
     4  ApiLatency        payments-tickets                   payments-oncall, payments-tickets
     3  IndexBehind       platform-weekend                   search-oncall
     3  LoadGenSaturated  payments-tickets                   blackhole
     3  ReplicationLag    payments-tickets, platform-oncall  dba-oncall, payments-tickets
     2  LoadGenSaturated  platform-weekend                   blackhole
     2  QueueDepth        payments-tickets, platform-oncall  payments-tickets
     2  ReplicationLag    platform-oncall, storage-oncall    dba-oncall, storage-oncall
     1  ApiLatency        payments-oncall, platform-oncall   payments-tickets
     1  ApiLatency        payments-tickets, platform-oncall  payments-oncall, payments-tickets
     1  ErrorRate         payments-tickets, platform-oncall  payments-tickets
     1  HighMemory        ops-pager                          platform-oncall
     1  HighMemory        platform-oncall, platform-weekend  platform-weekend
     1  NodeDown          ops-pager                          platform-oncall
     1  ProbeFailed       ops-pager                          platform-oncall
     1  ProbeFailed       platform-oncall, platform-weekend  platform-weekend
```

## Errors

Like pagerlog's other commands: a message on standard error starting with `pagerlog: `, nothing on standard output, and

- exit status 2 for a usage error: an unknown option, `--routes` missing, without its value, or given twice, or not exactly one `HISTORY`;
- exit status 1 when the routing file is not valid (`pagerlog: ` and then the error as docs/routing.md writes it, for example `pagerlog: routing/main.routes:12: unknown receiver "dba"`), when `HISTORY` cannot be read or is not a valid export (the same messages as `pagerlog check`), and when it has no alerts (`pagerlog: HISTORY: no alerts`). The routing file is read first, so when both files are bad, the routing file's error is the one reported.
