# Commit the fixture as the repository's history so far (semver, config, and gitx with `next`; then `notes`; then
# the tarball spec) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Mara Quist"
git config user.email "mara@tidewater.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2025-04-03T10:20:00Z "shipkit: next, from the release tags" .gitignore go.mod README.md internal cmd docs/next.md
commit 2025-06-11T16:05:00Z "notes: commits since the newest release" docs/notes.md
commit 2025-09-19T09:40:00Z "docs: tarball, as agreed in the release meeting" docs/tarball.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
