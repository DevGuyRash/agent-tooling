# Commit the fixture as the repository's history so far (the backend client and the book page, the server,
# then the backends' notes and the release) and publish it to a local origin.
set -e
git init -q -b main .
git config user.name "Larkspur Web"
git config user.email "web@larkspurbooks.example"
commit() {
	when=$1 message=$2
	shift 2
	git add -- "$@"
	GIT_AUTHOR_DATE=$when GIT_COMMITTER_DATE=$when git commit -q -m "$message"
}
commit 2026-04-14T10:20:00Z "Backend client on asyncio streams, and the book page" pyproject.toml .gitignore \
	storefront/__init__.py storefront/http.py storefront/backends.py storefront/book_page.py \
	tests/__init__.py tests/fakes.py tests/test_book_page.py tests/test_http.py
commit 2026-05-06T15:05:00Z "HTTP server for the API" storefront/__main__.py storefront/server.py tests/test_server.py
commit 2026-08-19T11:40:00Z "docs: the book page's backends, with staging latencies" docs
commit 2026-09-08T09:30:00Z "README and changelog for 1.6.0" README.md CHANGELOG.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
