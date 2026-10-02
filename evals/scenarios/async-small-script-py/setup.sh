# Commit the fixture as the repository's history so far (the crew list script, then the sample exports and the
# README) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Seeufer RC"
git config user.email "boathouse@seeufer-rc.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-03-08T18:20:00Z "crew_list.py for the noticeboard" scripts tests .gitignore
commit 2026-04-19T10:05:00Z "sample exports from the booking site; README" samples README.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
