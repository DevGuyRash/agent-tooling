# Commit the fixture as the repository's history so far (the label library and its command, then the API and
# fxd notes, then the 1.4.0 release) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Marktgasse IT"
git config user.email "it@marktgasse.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2025-11-04T09:20:00Z "shelftag: label text, money helpers, print and preview" pyproject.toml shelftag tests .gitignore
commit 2026-01-20T13:05:00Z "docs: the stable API and who calls it; the fxd protocol from the ops wiki" docs
commit 2026-06-02T08:45:00Z "README and changelog for 1.4.0" README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
