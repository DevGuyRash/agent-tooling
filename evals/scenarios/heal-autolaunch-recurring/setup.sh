# Rebuild the repository: four commits, the second renaming the docs check from `docs-check` to `lint-docs` while
# leaving AGENTS.md as it was. Then plant the observation that two earlier sessions left about it (here), or an empty
# observations directory (heal-autolaunch-first, which runs this script with HEAL_AUTOLAUNCH_OBSERVED=no).
# Everything is dated relative to now, so the history and the observation never drift apart however late this runs.
set -e
S="${HEAL_AUTOLAUNCH_SRC:-$(cd "$(dirname "$0")" && pwd)}"
H="$S/history"

cat > "$TRIAL_HARNESS/dates.py" <<'PY'
from datetime import datetime, timedelta, timezone

today = datetime.now(timezone.utc).date()


def at(days, time):
    return f"{(today - timedelta(days=days)).isoformat()}T{time}+00:00"


print(f"C0={at(52, '16:12:09')}")
print(f"C1={at(31, '10:41:37')}")
print(f"C2={at(14, '17:26:48')}")
print(f"C3={at(6, '15:03:21')}")
print(f"D_FIRST={(today - timedelta(days=14)).isoformat()}")
print(f"D_SECOND={(today - timedelta(days=6)).isoformat()}")
print(f"T_SECOND={(today - timedelta(days=6)).strftime('%Y%m%d')}1710")
PY
DATES="$(python3 "$TRIAL_HARNESS/dates.py")" || { echo "setup: computing the dates failed" >&2; exit 1; }
rm -f "$TRIAL_HARNESS/dates.py"
eval "$DATES"

FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
at() { export GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1"; }
commit() {  # SUBJECT [BODY]
  git add -A
  if [ -n "$2" ]; then git commit -q -m "$1" -m "$2"; else git commit -q -m "$1"; fi
}

# Everything is in its final state except the four files that changed after the first import.
cp -R "$H/c0/." .
at "$C0"; commit "chore: initial import"
cp "$FINAL/Makefile" Makefile
cp -R "$H/c1/." .
at "$C1"; commit "build: rename the docs-check target to lint-docs" "Same check, named like the lint-* targets we plan to add. README updated."
cp "$FINAL/chorelog/log.py" chorelog/log.py
cp "$FINAL/tests/test_log.py" tests/test_log.py
at "$C2"; commit "fix: ignore blank lines in the log"
cp "$FINAL/README.md" README.md
at "$C3"; commit "docs: describe the log format in the README"
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
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
rm -rf "$FINAL"

# The store of open observations: one file here, none in heal-autolaunch-first. The file as planted is kept in the
# harness so check.py can tell what a run added to it.
mkdir -p .local/observations
if [ "${HEAL_AUTOLAUNCH_OBSERVED:-yes}" = yes ]; then
  sed -e "s/@FIRST@/$D_FIRST/" -e "s/@SECOND@/$D_SECOND/" "$S/observation.md" \
    > .local/observations/agents-md-names-a-missing-make-target.md
  cp .local/observations/agents-md-names-a-missing-make-target.md "$TRIAL_HARNESS/observation-initial.md"
  touch -t "$T_SECOND" .local/observations/agents-md-names-a-missing-make-target.md  # last written in the second session
fi
touch -t "$T_SECOND" .local/observations
