# Rebuild the repository history: the library, the parallel test that turned out flaky, and the two
# speculative sleeps that were committed to deflake it. The last commit holds the fixture state.
set -e
S="$(cd "$(dirname "$0")" && pwd)"
H="$S/history"
FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
commit() {  # date author-name author-email subject [body]
  GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" GIT_AUTHOR_NAME="$2" GIT_AUTHOR_EMAIL="$3" \
    git commit -q -m "$4" ${5:+-m "$5"}
}

cp "$H/c1/eventspool/spool.py" eventspool/spool.py
cp "$H/c1/tests/test_spool.py" tests/test_spool.py
git add -A
commit "2026-09-02T10:14:07-07:00" "Mara Lind" "mara@acme.example" \
  "Add eventspool: batched background writing of audit events" \
  "Request handlers submit() audit events; one writer thread hands them to a sink in batches, so a slow collector never holds up a request. Includes MemorySink and JsonlSink."

cp "$FINAL/tests/test_spool.py" tests/test_spool.py
git add -A
commit "2026-09-08T16:41:52-07:00" "Mara Lind" "mara@acme.example" \
  "Test parallel producers against a stalling sink" \
  "Eight producer threads against a sink that, like the real collector, stalls a write now and then."

cp "$H/c3/eventspool/spool.py" eventspool/spool.py
git add -A
commit "2026-09-15T09:03:26-07:00" "Jon Ode" "jon@acme.example" \
  "Deflake test_parallel_producers: let the writer thread start first" \
  "CI failed it with 1584 != 1600. Maybe events submitted before the writer thread is running get lost."

cp "$FINAL/eventspool/spool.py" eventspool/spool.py
git add -A
commit "2026-09-23T14:27:45-07:00" "Jon Ode" "jon@acme.example" \
  "flush(): give the writer a moment to finish its last batch" \
  "test_parallel_producers still fails on CI now and then (1592 != 1600)."

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
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
rm -rf "$FINAL"
