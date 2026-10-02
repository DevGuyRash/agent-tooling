# Commit the fixture as the repository's history so far and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Tomasz Wrona"
git config user.email "tomasz@kestrelvalley-buses.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
commit "2026-05-19T16:40:00+01:00" "tapfare: fare rules and the nightly charge run for the route 12 pilot" \
  .gitignore package.json tsconfig.json bin src/money.ts src/serviceday.ts src/taps.ts src/fares.ts src/debits.ts \
  src/output.ts src/statement.ts src/cli.ts docs test/taps.test.ts test/fares.test.ts test/debits.test.ts
commit "2026-06-09T11:05:00+01:00" "CLI tests against the pilot's first billed day" test/cli.test.ts test/fixtures
commit "2026-06-09T11:30:00+01:00" "README" README.md
commit "2026-06-15T09:15:00+01:00" "Nightly cron job for fares-01" scripts/nightly.sh
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
