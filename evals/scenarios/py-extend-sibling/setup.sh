# Commit the fixture as the repository's history so far (deskd, support's SLA script, the image, the docs) and publish
# it to a local origin.
set -e
git init -q -b main .
git config user.name "Tomas Lindqvist"
git config user.email "tomas@northdesk.example"
commit() {  # DATE AUTHOR MESSAGE PATH...
	when=$1 author=$2 message=$3
	shift 3
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q --author "$author" -m "$message"
}
TOMAS="Tomas Lindqvist <tomas@northdesk.example>"
AMARA="Amara Osei <amara@northdesk.example>"
commit 2025-06-10T09:12:00Z "$TOMAS" "deskd: ticket API, export, and list over the nightly dump" \
	deskd tests pyproject.toml .gitignore config/deskd.conf
commit 2025-09-03T15:40:00Z "$AMARA" "tools: first-response due times for the breach report" \
	tools config/business-hours.conf config/holidays.txt config/sla-targets.conf docs/sla.md
commit 2026-01-20T11:05:00Z "$TOMAS" "Build the production image from distroless" Dockerfile
commit 2026-09-14T10:30:00Z "$AMARA" "Calendar: autumn and winter holidays" config/holidays.txt README.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
