# Commit the fixture as the repository's history so far (the readers, the commands, then the waves spec) and
# publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Kestrel Warehouse"
git config user.email "warehouse@kestrel.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-04-14T07:10:00Z "orders and stock readers, bins and walking order" go.mod internal .gitignore
commit 2026-04-15T16:30:00Z "pickctl: stock and check" cmd testdata
commit 2026-07-21T06:50:00Z "README and changelog for 0.3.0" README.md CHANGELOG.md
commit 2026-09-28T12:05:00Z "docs: Marta's rules for picking waves" docs
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
