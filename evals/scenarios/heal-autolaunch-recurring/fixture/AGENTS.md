# chorelog agent notes

chorelog keeps a household chore log in a plain text file. Python 3.11+, standard library only.

- Run `make test` and `make docs-check` before committing.
- Use conventional commit subjects (`feat:`, `fix:`, `docs:`, `build:`).
- Local working records, notes and observations included, go in `.local/` (git-ignored).

## Layout

- `chorelog/log.py`: reading and writing the log file.
- `chorelog/report.py`: counting entries.
- `chorelog/cli.py`: the `add` and `report` commands.
- `scripts/check_docs.py`: the docs check.
- `tests/`: unittest suites, one file per module.
