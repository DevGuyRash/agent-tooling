# Commit the fixture as the repository's history so far (the hub client and the list and read commands, the
# hub's protocol notes, then the status command for the availability map) and publish it to a local origin.
# .history holds the files as they were before `status`; it is not part of the repository.
set -e
git init -q -b main .
git config user.name "Priya Raman"
git config user.email "praman@brightwater-charge.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
final=$(mktemp -d)
cp -R src test README.md CHANGELOG.md package.json "$final/"
cp -R .history/. .
rm -rf .history
commit 2025-08-12T15:10:00Z "plugctl 2.0: TypeScript, list and read" package.json tsconfig.json .gitignore bin src test
commit 2025-08-12T15:40:00Z "docs: the hub's line protocol, from the vendor's integration guide" docs
commit 2025-12-02T09:20:00Z "README and changelog for 2.2.0" README.md CHANGELOG.md
rm -rf src test
cp -R "$final/." .
rm -rf "$final"
commit 2026-05-27T11:05:00Z "plugctl status for the availability map" package.json src test README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
