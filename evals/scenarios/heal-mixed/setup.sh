# Rebuild the repository history the session logs describe, then leave the
# worktrees and branches those sessions left behind.
set -e
S="$(cd "$(dirname "$0")" && pwd)"
H="$S/history"
FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
at() { export GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1"; }
put() { src=$1; shift; for rel; do mkdir -p "$(dirname "$rel")"; cp "$src/$rel" "$rel"; done; }
commit() { git add -A && git commit -q --no-verify -m "$1"; }

# 0.6.0
rm -f tests/helpers.py
cp -R "$H/c1/." .
at "2026-08-30T16:40:00-07:00"; commit "chore: release 0.6.0"

# fix/isbn-x-check-digit: merged, worktree and branch left behind
git switch -q -c fix/isbn-x-check-digit
put "$FINAL" shelfmark/isbn.py tests/test_isbn.py
cp "$H/c2/CHANGELOG.md" CHANGELOG.md
cp "$H/c2/tests/test_cli.py" tests/test_cli.py
at "2026-09-02T09:31:12-07:00"; commit "chore: Accept X as the ISBN-10 check digit"
git switch -q main && git merge -q --ff-only fix/isbn-x-check-digit

# refactor/test-helpers: merged and cleaned up
git switch -q -c refactor/test-helpers
put "$FINAL" tests/helpers.py
cp "$H/c3/tests/test_catalog.py" tests/test_catalog.py
cp "$H/c3/CHANGELOG.md" CHANGELOG.md
at "2026-09-04T14:12:40-07:00"; commit "fix: share catalog test fixtures via helper"
git switch -q main && git merge -q --ff-only refactor/test-helpers && git branch -q -d refactor/test-helpers

# docs/export-typo: merged and cleaned up
git switch -q -c docs/export-typo
put "$FINAL" docs/commands.md
at "2026-09-08T11:05:31-07:00"; commit "docs: fix --format typo in export section"
git switch -q main && git merge -q --ff-only docs/export-typo && git branch -q -d docs/export-typo

# feat/tag-command: merged, worktree and branch left behind
git switch -q -c feat/tag-command
put "$FINAL" shelfmark/cli.py shelfmark/catalog.py tests/test_catalog.py tests/test_cli.py CHANGELOG.md
at "2026-09-10T15:48:02-07:00"; commit "feat: Add tag command"
git switch -q main && git merge -q --ff-only feat/tag-command

if ! diff -r -q -x .git -x .local . "$FINAL" >/dev/null; then
  diff -r -q -x .git -x .local . "$FINAL" >&2
  echo "setup: rebuilt history does not end at the fixture state" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  git status --porcelain >&2
  echo "setup: the last commit does not hold the fixture state" >&2
  exit 1
fi

git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main fix/isbn-x-check-digit feat/tag-command 2>/dev/null

git worktree add -q ../shelfmark-isbn-x fix/isbn-x-check-digit
git worktree add -q ../shelfmark-tag-command feat/tag-command

# spike/sqlite-store: parked by the developer, unmerged, with uncommitted work
git worktree add -q -b spike/sqlite-store ../shelfmark-sqlite-spike main
cp "$S/spike/store_sqlite.py" ../shelfmark-sqlite-spike/shelfmark/store_sqlite.py
at "2026-09-12T10:22:57-07:00"
(cd ../shelfmark-sqlite-spike && git add -A && git commit -q --no-verify -m "feat: Add SQLite store spike")
cp "$S/spike/catalog.py" ../shelfmark-sqlite-spike/shelfmark/catalog.py
unset GIT_AUTHOR_DATE GIT_COMMITTER_DATE

chmod +x .githooks/commit-msg
git config core.hooksPath .githooks
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
git rev-parse spike/sqlite-store > "$TRIAL_HARNESS/spike-head"
rm -rf "$FINAL"
