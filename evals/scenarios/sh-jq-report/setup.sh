# Commit the fixture as the repository's history so far (the report and its config; the report's docs; then the
# spec of the new section) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Larkspur Edge"
git config user.email "edge-team@larkspur.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
full=$(mktemp)
cp docs/daily-report.md "$full"
awk '/^## Tenants over budget/ { exit } { line[++n] = $0 }
	END { while (n > 0 && line[n] == "") n--; for (i = 1; i <= n; i++) print line[i] }' "$full" > docs/daily-report.md
commit 2025-06-02T08:30:00Z "daily edge report: summary, status classes, top routes and tenants" .gitignore \
	README.md ops scripts config docs/log-format.md samples tests
commit 2025-08-19T14:05:00Z "docs: what each section of the daily report shows" docs/daily-report.md
cp "$full" docs/daily-report.md
rm -f "$full"
commit 2025-09-26T10:12:00Z "docs: tenants over budget, as agreed with support" docs/daily-report.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
