# Commit the fixture as the repository's history so far and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Ines Castro"
git config user.email "ines@acme.example"
commit() {  # DATE MESSAGE PATH...
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-03-02T09:05:00Z "runner-usage: runner minutes per team from the CI export, against the budgets" scripts tests
commit 2026-06-18T14:40:00Z "README: runner-usage and its tests" README.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
