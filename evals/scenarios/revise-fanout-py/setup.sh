# Commit the fixture as the repository's history so far (the client and the units and temp commands, the
# gateway's API notes, then the check command for the food-safety monitor) and publish it to a local origin.
# .history holds the files as they were before `check`; it is not part of the repository.
set -e
git init -q -b main .
git config user.name "Dana Okafor"
git config user.email "dokafor@larchmont-grocers.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
final=$(mktemp -d)
cp -R coldctl tests README.md CHANGELOG.md pyproject.toml "$final/"
cp -R .history/. .
rm -rf .history
commit 2025-11-04T16:20:00Z "coldctl: units and temp" pyproject.toml coldctl tests .gitignore
commit 2026-01-20T10:05:00Z "docs: the BMS gateway's API, from the vendor reference" docs
commit 2026-01-20T10:30:00Z "README and changelog for 0.4.0" README.md CHANGELOG.md
rm -rf coldctl tests
cp -R "$final/." .
rm -rf "$final"
commit 2026-04-14T13:45:00Z "coldctl check for the food-safety monitor" pyproject.toml coldctl tests README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
