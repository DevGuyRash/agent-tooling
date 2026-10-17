# chorelog

Keep a household chore log in a plain text file and see who did what.

```sh
chorelog add mara dishes --date 2026-09-14
chorelog add ines "take out the trash"
chorelog report
```

`chorelog add` appends an entry, dated today unless `--date` says otherwise. `chorelog report` prints how many entries each person has, most first. The log is `chores.log` in the current directory; `--file` picks another.

## Development

- `make test` runs the unit tests.
- `make docs-check` checks that this file documents every command.
- Notes for coding agents are in `AGENTS.md`.
