# Commit the fixture as the repository's history so far (the gateway client and commands, then the
# gateway's API notes) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Riverbend Ops"
git config user.email "ops@riverbend.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-03-02T10:15:00Z "dockctl: list and show" pyproject.toml dockctl tests .gitignore
commit 2026-05-19T14:40:00Z "docs: the dock gateway's API, from the vendor reference" docs
commit 2026-07-08T09:05:00Z "README and changelog for 0.4.0" README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
