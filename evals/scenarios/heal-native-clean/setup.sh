# Rebuild the repository history the session logs describe.
set -e
S="$(cd "$(dirname "$0")" && pwd)"
H="$S/history"

# Commit dates, tag dates, and the CHANGELOG.md release headings are all computed from one shared "now"
# (native_logs.py's `dates`), the same anchor the six sessions below use: a fixed calendar date here would
# drift further from the sessions' relative-to-now dates every day this scenario is later run (see
# qualify/README.md). Captured into a variable first, not "eval $(...)" directly: a failure inside a bare
# "eval $(cmd)" does not itself fail the script under "set -e" (eval's own, usually-zero exit status is all
# "set -e" would see), so a broken `dates` call would otherwise leave every DATE variable unset instead of
# stopping setup here.
ANCHOR="$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')"
DATES_OUT="$(python3 "$S/native_logs.py" dates "$ANCHOR")" \
  || { echo "setup: computing commit dates failed" >&2; exit 1; }
eval "$DATES_OUT"

# CHANGELOG.md's own two release headings ("2026-08-24" and "2026-09-09" in the checked-in fixture and
# history/ states) are sentinels, substituted here for the real, "now"-relative date computed above; called
# again after every `state` below because each history/cN state re-copies its own CHANGELOG.md snapshot
# (still carrying the sentinel dates) on top of the working tree.
datestamp() { [ -f CHANGELOG.md ] && sed -i "s/2026-08-24/$V030_DATE/g; s/2026-09-09/$V040_DATE/g" CHANGELOG.md; true; }
datestamp   # the freshly-seeded fixture's own CHANGELOG.md, before it is snapshotted as FINAL below

FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
at() { export GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1"; }
state() { cp -R "$H/$1/." .; datestamp; }
commit() { git add -A && git commit -q -m "$1"; }
branch_commit() {  # branch date message: commit on a branch, fast-forward main, delete the branch
  git switch -q -c "$1"; at "$2"; commit "$3"; git switch -q main
  git merge -q --ff-only "$1"; git branch -q -d "$1"
}

state c0; at "$V030_COMMIT"; commit "chore: release 0.3.0"
git tag -a v0.3.0 -m "pantry 0.3.0"
state c1; branch_commit feat/metric "$METRIC_COMMIT" "feat: add scale --metric"
state c2; at "$DOCS_COMMIT"; commit "docs: describe the recipe format"
state c3; branch_commit fix/mixed-numbers "$MIXED_COMMIT" "fix: parse mixed numbers like 1 1/2"
state c4; at "$V040_COMMIT"; commit "chore: release 0.4.0"
git tag -a v0.4.0 -m "pantry 0.4.0"
state c5; branch_commit feat/ounces "$OUNCES_COMMIT" "feat: convert ounces and pounds"
unset GIT_AUTHOR_DATE GIT_COMMITTER_DATE

if ! diff -r -q -x .git . "$FINAL" >/dev/null; then
  diff -r -q -x .git . "$FINAL" >&2
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

# The six sessions land where Codex and Claude Code actually keep their own records - under the run's
# private $HOME (already set by the runtime, not this repository) - dated within the past week of right
# now (the same $ANCHOR the commit dates above use, so the two never drift apart), and their own recorded
# cwd is this checkout's real, resolvable path ($PWD), not a fictional one, so a gatherer that reads a
# session's own recorded working directory finds an actual git repository (see native_logs.py). The
# checksum ledger native_logs.py writes for check.py's native_logs_unchanged lands one level above
# $TRIAL_HARNESS - outside the directory both executors are given as "--add-dir" - under a name that says
# nothing about what it is.
python3 "$S/native_logs.py" write "$HOME" "$(dirname "$TRIAL_HARNESS")/.session-checksums" "$PWD" "$ANCHOR" >/dev/null
