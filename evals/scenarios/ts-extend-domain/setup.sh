# Commit the fixture as the repository's history so far (the cataloguers' checks first, then shelfwise, the README,
# and Mei's spec for the new command) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Ruth Adeyemi"
git config user.email "ruth@larkfield-libraries.example"
commit() {  # DATE AUTHOR MESSAGE PATH...
	when=$1 author=$2 message=$3
	shift 3
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q --author "$author" -m "$message"
}
PAVEL="Pavel Novak <pavel@larkfield-libraries.example>"
RUTH="Ruth Adeyemi <ruth@larkfield-libraries.example>"
MEI="Mei Tanaka <mei@larkfield-libraries.example>"
commit 2024-11-18T14:20:00Z "$PAVEL" "catalog: call-number checks and inventory shelf lists" catalog ops docs/callnumbers.md
commit 2026-02-09T10:45:00Z "$RUTH" "shelfwise: holds lists and export checks for the desks" \
	package.json tsconfig.json .gitignore bin src test
commit 2026-02-10T09:00:00Z "$RUTH" "README: shelfwise and the catalog checks" README.md
commit 2026-09-30T16:10:00Z "$MEI" "docs: what the morning pull list should look like" docs/pull.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
