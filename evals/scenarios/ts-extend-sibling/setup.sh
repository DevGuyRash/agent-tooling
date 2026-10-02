# Commit the fixture as the repository's history so far (the month-end invoice script first, then hours, the
# September timesheets, the README, and Dana's spec for the new command) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Omar Haddad"
git config user.email "omar@brightwater.example"
commit() {  # DATE AUTHOR MESSAGE PATH...
	when=$1 author=$2 message=$3
	shift 3
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q --author "$author" -m "$message"
}
DANA="Dana Okafor <dana@brightwater.example>"
OMAR="Omar Haddad <omar@brightwater.example>"
commit 2025-01-30T17:40:00Z "$DANA" "Month-end invoices from the timesheets and the rate card" \
	scripts ops rates.txt docs/rates.md docs/timesheets.md
commit 2026-04-14T15:05:00Z "$OMAR" "hours: check timesheets and report time per project, client, or date" \
	package.json tsconfig.json .gitignore bin src test
commit 2026-09-01T08:30:00Z "$DANA" "September timesheets" timesheets
commit 2026-09-02T10:12:00Z "$OMAR" "README: hours and the month-end invoices" README.md
commit 2026-09-28T16:48:00Z "$DANA" "docs: what hours invoice should print" docs/invoice.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
