# Commit the fixture as the repository's history so far (the nightly prune script first, then bakctl, then
# the spec for the new subcommand) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Tidewater Ops"
git config user.email "ops@tidewater.example"
commit() {
	when=$1 author=$2 message=$3
	shift 3
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q --author "$author" -m "$message"
}
commit 2025-04-08T09:20:00Z "Storage Team <storage@tidewater.example>" \
	"nightly prune: pick the snapshots to delete by retention policy" scripts ops
commit 2026-06-16T14:05:00Z "Tidewater Ops <ops@tidewater.example>" \
	"catalog: reader for the storage servers' nightly export" go.mod internal/catalog
commit 2026-06-18T10:42:00Z "Tidewater Ops <ops@tidewater.example>" \
	"bakctl: list, usage, and check subcommands" internal/humanize internal/report cmd
commit 2026-06-18T11:10:00Z "Tidewater Ops <ops@tidewater.example>" \
	"README: bakctl and the nightly prune" README.md .gitignore
commit 2026-09-24T16:31:00Z "Tidewater Ops <ops@tidewater.example>" \
	"docs: spec for bakctl prune (#41)" docs
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
