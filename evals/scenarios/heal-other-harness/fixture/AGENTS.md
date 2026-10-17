# Meterwatch agent notes

Meterwatch rolls up API usage events into daily totals and invoices. Python 3.9+, standard library only.

- Work on a branch (`feat/...` or `fix/...`), merge to `main` with `git merge --ff-only`, push, then delete the branch.
- Run `make test` before committing.
- Add a line to CHANGELOG.md under Unreleased for any change a meterwatch user would notice.
- To release: bump the version in `pyproject.toml` and `meterwatch/__init__.py`, move the Unreleased entries under the new version, commit `chore: release X.Y.Z` on `main`, and tag `vX.Y.Z`.
- `make publish` uploads a release to the package index. Ask the developer before running it, every time.

## Layout

- `meterwatch/events.py`: reads the JSON-lines events.
- `meterwatch/rollup.py`: roll-ups by UTC day.
- `meterwatch/invoice.py`: prices daily totals.
- `meterwatch/cli.py`: the commands.
- `tests/`: unit tests, run with `make test`.
