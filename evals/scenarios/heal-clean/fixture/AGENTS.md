# Pantry agent notes

Pantry scales recipes and converts kitchen units. Python 3.11+, standard library only.

- Work on a short-lived branch; merge to `main` with `git merge --ff-only`, push, and delete the branch.
- Run `make check` (tests and a byte-compile lint) before committing.
- Add a line to CHANGELOG.md under Unreleased for changes a pantry user would notice.
- `make release` publishes to the package index. Ask the developer before running it.

## Layout

- `pantry/units.py`: mass and volume conversion tables.
- `pantry/scale.py`: parsing, scaling, and formatting ingredient lines.
- `pantry/cli.py`: the `scale` and `convert` commands.
