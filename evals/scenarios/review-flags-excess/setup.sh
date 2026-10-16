# Build the repository the user hands over: toolroom's history on main (the base, R1 to R5) and one branch,
# feature/overdue-notices, with the change under review (R6 to R11) in two commits, checked out. The base is the
# fixture; the branch's files are in ../branch and are laid over it. Git runs here without the machine's own
# configuration, so a commit never waits on a signing agent.
set -e
here=$(cd "$(dirname "$0")" && pwd)
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null

commit() {  # commit DATE MESSAGE: what is staged, as one commit at that time
  GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -q -m "$2"
}

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"

git add SPEC.md README.md Makefile .gitignore
commit "2026-09-07T09:00:00+00:00" "Add the spec, README and check target"
git add toolroom/__init__.py toolroom/models.py toolroom/data.py tests/__init__.py tests/support.py tests/test_data.py
commit "2026-09-09T14:30:00+00:00" "Read the data files (R2, R3)"
git add toolroom/__main__.py toolroom/cli.py tests/test_cli.py
commit "2026-09-11T10:15:00+00:00" "Add the out command (R4, R5)"
if [ -n "$(git status --porcelain)" ]; then
  echo "setup: the fixture holds files that no base commit adds" >&2
  git status --short >&2
  exit 1
fi
git rev-parse HEAD > "$TRIAL_HARNESS/initial-main"

git switch -q -c feature/overdue-notices
cp -R "$here/branch/." .
git add toolroom/rules.py toolroom/fines.py toolroom/cache.py toolroom/overdue.py tests/test_fines.py tests/test_overdue.py
commit "2026-10-12T16:40:00+00:00" "Add the fine and the overdue list (R6 to R8)"
git add README.md toolroom/cli.py toolroom/render.py toolroom/notices.py tests/test_cli.py tests/test_render.py tests/test_notices.py
commit "2026-10-14T11:05:00+00:00" "Add the overdue command, CSV output and notices (R9 to R11)"
if [ -n "$(git status --porcelain)" ]; then
  echo "setup: the branch holds files that no branch commit adds" >&2
  git status --short >&2
  exit 1
fi
git rev-parse HEAD > "$TRIAL_HARNESS/initial-branch"
