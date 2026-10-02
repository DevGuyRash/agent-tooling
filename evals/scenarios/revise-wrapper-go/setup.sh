# Commit the fixture as the operator's history so far (the log reader, check and day, then punctuality with its
# figures from Ailsa's script, then the week's logs and the README) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Calum Rennie"
git config user.email "calum@inchmara-ferries.example"
commit() {  # DATE AUTHOR MESSAGE PATH...
  d="$1"
  a="$2"
  m="$3"
  shift 3
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q --author "$a" -m "$m"
}
commit "2026-05-11T09:15:00+01:00" "Calum Rennie <calum@inchmara-ferries.example>" \
  "ferry: crossing logs, check and day" go.mod .gitignore internal cmd/ferry/main.go docs/log-format.md
commit "2026-06-02T16:40:00+01:00" "Ailsa Munro <ailsa@inchmara-ferries.example>" \
  "Punctuality figures (scripts/punctuality.py)" scripts
commit "2026-06-03T11:05:00+01:00" "Calum Rennie <calum@inchmara-ferries.example>" \
  "ferry punctuality: lay out Ailsa's figures" cmd/ferry/punctuality.go cmd/ferry/main_test.go docs/punctuality.md
commit "2026-09-21T08:30:00+01:00" "Calum Rennie <calum@inchmara-ferries.example>" \
  "Logs for the week of 14 September" logs
commit "2026-09-21T08:45:00+01:00" "Calum Rennie <calum@inchmara-ferries.example>" \
  "README" README.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
