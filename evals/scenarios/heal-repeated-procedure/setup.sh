# Rebuild the repository history the session logs describe.
set -e
S="$(cd "$(dirname "$0")" && pwd)"
H="$S/history"
FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
at() { export GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1"; }
state() { cp -R "$H/$1/." .; }
commit() { git add -A && git commit -q -m "$1"; }
branch_commit() {  # branch date message: commit on a branch, fast-forward main, delete the branch
  git switch -q -c "$1"; at "$2"; commit "$3"; git switch -q main
  git merge -q --ff-only "$1"; git branch -q -d "$1"
}

rm -f tests/golden/*.json.bak tests/golden/*.json.new
state c0; at "2026-08-28T17:05:44-07:00"; commit "chore: release 0.8.0"
state c1; branch_commit feat/collapse-whitespace "2026-09-01T09:14:51-07:00" "feat: collapse whitespace in descriptions"
state c2; cp "$FINAL/tests/golden/ally_savings.json.bak" tests/golden/
branch_commit feat/schwab-dividends "2026-09-03T15:40:17-07:00" "feat: categorize Schwab dividends as income"
state c3; cp "$FINAL/tests/golden/chase_refunds.json.new" tests/golden/
branch_commit fix/chase-refunds "2026-09-05T11:27:03-07:00" "fix: report Chase refunds as positive credits"
state c4; branch_commit fix/schwab-parens "2026-09-09T14:02:38-07:00" "fix: parse parenthesized Schwab amounts as negative"
state c5; at "2026-09-12T10:31:09-07:00"; commit "chore: release 0.9.0"
git tag -a v0.9.0 -m "ledgerline 0.9.0"
state c6; branch_commit feat/strip-card-numbers "2026-09-18T16:12:26-07:00" "feat: strip masked card numbers from descriptions"
unset GIT_AUTHOR_DATE GIT_COMMITTER_DATE

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
git push -q -u origin main --tags 2>/dev/null
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
rm -rf "$FINAL"
