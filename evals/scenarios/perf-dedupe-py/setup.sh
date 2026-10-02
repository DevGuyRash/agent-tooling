# Commit the fixture as the repository's history so far, in the order the shop wrote it, and publish it to a
# local origin.
set -e
git init -q -b main .
git config user.name "Jon Ellery"
git config user.email "jon@larkspur-tea.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
commit "2025-11-03T20:14:00+00:00" "shopcrm: validate, lookup, and stats for the storefront export" \
  .gitignore pyproject.toml shopcrm tests/__init__.py tests/test_money.py tests/data docs/export-format.md
commit "2026-01-17T11:02:00+00:00" "Tests for contact matching and the commands" tests/test_contacts.py tests/test_cli.py
commit "2026-02-08T09:45:00+00:00" "Nightly sync script for the ops box" ops/nightly-sync.sh README.md
git add docs/dedupe.md
GIT_AUTHOR_NAME="Priya Raman" GIT_AUTHOR_EMAIL="priya@larkspur-tea.example" \
  GIT_AUTHOR_DATE="2026-09-28T16:30:00+00:00" GIT_COMMITTER_DATE="2026-09-28T16:30:00+00:00" \
  git commit -q -m "docs: how to collapse the export to one row per person"
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
