# chorelog

Keep a household chore log in a plain text file and see who did what.

```sh
chorelog add mara dishes --date 2026-09-14
chorelog add ines "take out the trash"
chorelog report
```

`chorelog add` appends an entry, dated today unless `--date` says otherwise. `chorelog report` prints how many entries each person has, most first. The log is `chores.log` in the current directory; `--file` picks another.

## Log format

One entry per line: an ISO date, the person (one word), and the chore (the rest of the line). Blank lines are ignored.

```
2026-09-14 mara dishes
2026-09-14 ines take out the trash
```

## Development

- `make test` runs the unit tests.
- `make lint-docs` checks that this file documents every command.
- Notes for coding agents are in `AGENTS.md`.
