# Ledgerline agent notes

Ledgerline turns bank CSV exports into one normalized ledger format. Python 3.11+, standard library only.

- Work on a branch, merge to `main` with `git merge --ff-only`, push, then delete the branch.
- Run `make test` before committing.
- A change to parsing or normalization changes the golden files in `tests/golden/`. Regenerate them as CONTRIBUTING.md describes and commit them with the change.
- Add a line to CHANGELOG.md under Unreleased for any change a ledgerline user would notice.
- `make publish` uploads a release to the package index. Ask the developer before running it.

## Layout

- `ledgerline/banks.py`: each bank's CSV columns and date format.
- `ledgerline/normalize.py`: row parsing, amounts, descriptions, categories.
- `ledgerline/cli.py`: the `normalize` command.
- `tests/data/<bank>_<name>.csv`: sample exports; `tests/golden/<bank>_<name>.json`: expected output.
