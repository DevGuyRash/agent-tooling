# Rebuild the repository history the Goose sessions describe, then plant the sessions themselves where Goose keeps
# them, in the run's own private home (see the last lines of this file and goose_sessions.py).
set -e
S="$(cd "$(dirname "$0")" && pwd)"
H="$S/history"

# Commit, tag, and CHANGELOG.md dates come from the same anchor as the session times, so the rebuilt history and the
# sessions that narrate it always agree, whenever this trial runs. Captured into a variable first, not "eval $(...)"
# directly: a failure inside a bare "eval $(cmd)" does not fail the script under "set -e".
ANCHOR="$(python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')"
DATES_OUT="$(python3 "$S/goose_sessions.py" dates "$ANCHOR")" \
  || { echo "setup: computing the commit dates failed" >&2; exit 1; }
eval "$DATES_OUT"

# CHANGELOG.md's three release dates are sentinels in fixture/ and history/. They are replaced here, once for each copy that
# carries them: through placeholders, because a real date may equal another sentinel, and never on a file that was already
# replaced.
fix_changelog() {
  [ -f CHANGELOG.md ] || return 0
  sed -i "s/2026-09-01/@FIRST@/g; s/2026-09-26/@BASE@/g; s/2026-10-13/@RELEASE@/g; s/@FIRST@/$D_FIRST/g; s/@BASE@/$D_BASE/g; s/@RELEASE@/$D_RELEASE/g" CHANGELOG.md
}
fix_changelog
FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
state() { cp -R "$H/$1/." .; if [ -f "$H/$1/CHANGELOG.md" ]; then fix_changelog; fi; }
# commit KEY: the author and committer dates and the subject that goose_sessions.py chose for it
commit() {
  K="$1"
  eval "A=\$C_${K}_AUTHOR; C=\$C_${K}_COMMITTER; M=\$S_${K}"
  git add -A
  GIT_AUTHOR_DATE="$A" GIT_COMMITTER_DATE="$C" git commit -q -m "$M"
}
# branch_commit KEY: commit on the session's branch, fast-forward main, delete the branch
branch_commit() {
  K="$1"
  eval "B=\$B_${K}"
  git switch -q -c "$B"; commit "$K"; git switch -q main
  git merge -q --ff-only "$B"; git branch -q -d "$B"
}

state c0; commit BASE
GIT_COMMITTER_DATE="$C_BASE_COMMITTER" git tag -a v0.2.0 -m "meterwatch 0.2.0"
state c1; branch_commit KEYFILTER
state c2; branch_commit TOP
state c3; commit DOCS
state c4; commit INVOICE
state c5; branch_commit TOTAL
state c6; commit RELEASE
GIT_COMMITTER_DATE="$C_RELEASE_COMMITTER" git tag -a v0.3.0 -m "meterwatch 0.3.0"
state c7; branch_commit SINCE

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

git init -q --bare -b main "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main --tags 2>/dev/null
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
rm -rf "$FINAL"

# The seven sessions, as Goose records them: one JSON Lines file per session under
# $HOME/.local/share/goose/sessions/, named by the machine's local start time. Their times are relative to the
# same anchor as the commits above, inside the last week, and their recorded working directory is this checkout.
# The checksum ledger check.py verifies them against lands one level above $TRIAL_HARNESS, outside the directory
# the executors are given, under a name that says nothing about what it is, keyed by the hash of each path.
python3 "$S/goose_sessions.py" render "$ANCHOR" "$HOME" "$(dirname "$TRIAL_HARNESS")/.session-checksums" "$(pwd)"
