# Shelfmark agent notes

Shelfmark is a small command-line catalogue for a home library. Python 3.11+, standard library only.

## Workflow

- Start every task in a fresh worktree: `git worktree add ../shelfmark-<task> -b <type>/<task>`.
- Run `make check` before committing; it runs the tests and the docs check.
- Update CHANGELOG.md for every change.
- Commit messages are typed automatically by the commit-msg hook (`.githooks/commit-msg`), so write a plain subject line.
- Merge finished branches into `main` with `git merge --ff-only` and push.

## Layout

- `shelfmark/cli.py`: argument parsing and command dispatch.
- `shelfmark/catalog.py`: the JSON catalogue file and book records.
- `shelfmark/isbn.py`: ISBN-10/13 validation.
- `docs/commands.md`: one `## <command>` section per CLI command.
