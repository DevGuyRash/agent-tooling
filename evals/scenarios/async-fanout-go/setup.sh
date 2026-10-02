# Commit the fixture as the repository's history so far (the gateway client and fake, the command, then the
# protocol notes) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Hollow Creek Ops"
git config user.email "ops@hollowcreek.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-02-11T09:30:00Z "gateway: client for the SCADA gateway's text protocol, and a fake for tests" go.mod internal .gitignore
commit 2026-02-12T15:10:00Z "farmctl: list and read" cmd
commit 2026-04-27T11:45:00Z "docs: the gateway's text protocol, from the vendor manual" docs
commit 2026-08-03T16:20:00Z "README and changelog for 0.3.0" README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
