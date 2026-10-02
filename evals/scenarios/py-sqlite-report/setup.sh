# Commit the fixture as the repository's history so far (the tool with its stations and bike commands, then the
# rebalance spec) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Tidewater Bikes Dispatch"
git config user.email "dispatch@tidewaterbikes.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2025-07-03T15:40:00Z "dockops: stations and bike commands over the trips database" .gitignore README.md dockops \
	scripts tests docs/database.md
commit 2025-09-24T11:02:00Z "docs: rebalance report as agreed with the van crews" docs/rebalance.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
