# Commit the fixture as the repository's history so far (the export reader and the code derivation, the
# turnstile list and the commands, the stadium's zones, then the docs and the release) and publish it to a
# local origin.
set -e
git init -q -b main .
git config user.name "Northgate Park IT"
git config user.email "it@northgatepark.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-01-20T10:00:00Z "sales export reader and gatepass/v2 codes" go.mod .gitignore internal/sales \
	internal/passcode
commit 2026-01-22T16:30:00Z "turnstile list with reissues; build and verify commands" internal/issue cmd testdata
commit 2026-06-30T09:15:00Z "docs: codes, the sales export, and event-day operations" docs
commit 2026-07-14T14:45:00Z "README and changelog for 2.1.0 (stadium zones)" README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
