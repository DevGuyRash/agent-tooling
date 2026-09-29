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

state c0; at "2026-08-24T18:02:10-07:00"; commit "chore: release 0.3.0"
git tag -a v0.3.0 -m "pantry 0.3.0"
state c1; branch_commit feat/metric "2026-09-02T10:07:45-07:00" "feat: add scale --metric"
state c2; at "2026-09-05T08:51:30-07:00"; commit "docs: describe the recipe format"
state c3; branch_commit fix/mixed-numbers "2026-09-05T09:26:12-07:00" "fix: parse mixed numbers like 1 1/2"
state c4; at "2026-09-09T13:12:40-07:00"; commit "chore: release 0.4.0"
git tag -a v0.4.0 -m "pantry 0.4.0"
state c5; branch_commit feat/ounces "2026-09-11T16:38:02-07:00" "feat: convert ounces and pounds"
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
