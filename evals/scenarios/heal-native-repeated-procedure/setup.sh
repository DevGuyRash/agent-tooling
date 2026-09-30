# Rebuild the repository history the session logs describe.
set -e
S="$(cd "$(dirname "$0")" && pwd)"
H="$S/history"
FINAL="$(mktemp -d "$TRIAL_HARNESS/final.XXXXXX")"
cp -a . "$FINAL/"

# Every "at" date below, the tag (it inherits GIT_COMMITTER_DATE from the release commit), and the
# two release dates baked into CHANGELOG.md shift by the same number of days, so the rebuilt history
# stays recent relative to whenever this trial actually runs instead of freezing at a fixed 2026
# calendar (which would only fall further behind "now" with every later trial) - the ledgerline
# session logs land on a similarly "recent" window for the same reason (see gen_native_logs.py). The
# shift keeps every date's original time of day and the story's original day-to-day spacing; only the
# calendar lands differently. c6, the last historical commit, is placed one day before "now".
SHIFT_DAYS=$(( ( $(date -u -d "$(date -u +%Y-%m-%d)" +%s) - $(date -u -d "2026-09-19" +%s) ) / 86400 ))
date_shift() { date -d "$1 +${SHIFT_DAYS} days" +%Y-%m-%dT%H:%M:%S%:z; }
changelog_date_shift() { date -d "$1 +${SHIFT_DAYS} days" +%Y-%m-%d; }
D_0_8_0="$(changelog_date_shift 2026-08-28)"
D_0_9_0="$(changelog_date_shift 2026-09-12)"
fix_changelog() { [ -f CHANGELOG.md ] && sed -i "s/2026-08-28/$D_0_8_0/g; s/2026-09-12/$D_0_9_0/g" CHANGELOG.md; }
# $FINAL was copied from the plain (unshifted) fixture state above; shift its dates the same way so
# the rebuilt tree's self-check below still finds the two identical.
[ -f "$FINAL/CHANGELOG.md" ] && sed -i "s/2026-08-28/$D_0_8_0/g; s/2026-09-12/$D_0_9_0/g" "$FINAL/CHANGELOG.md"

git init -q -b main .
git config user.name "Acme Dev"
git config user.email "dev@acme.example"
at() { export GIT_AUTHOR_DATE="$(date_shift "$1")" GIT_COMMITTER_DATE="$(date_shift "$1")"; }
state() { cp -R "$H/$1/." .; fix_changelog; }
commit() { git add -A && git commit -q -m "$1"; }
branch_commit() {  # branch date message: commit on a branch, fast-forward main, delete the branch
  git switch -q -c "$1"; at "$2"; commit "$3"; git switch -q main
  git merge -q --ff-only "$1"; git branch -q -d "$1"
}

rm -f tests/golden/*.json.bak tests/golden/*.json.new
state c0; at "2026-08-28T17:05:44-07:00"; commit "chore: release 0.8.0"
state c1; branch_commit feat/collapse-whitespace "2026-09-01T09:14:51-07:00" "feat: collapse whitespace in descriptions"
state c2; cp "$FINAL/tests/golden/ally_savings.json.bak" tests/golden/
branch_commit feat/schwab-dividends "2026-09-03T15:40:17-07:00" "feat: categorize Schwab dividends as income"
state c3; cp "$FINAL/tests/golden/chase_refunds.json.new" tests/golden/
branch_commit fix/chase-refunds "2026-09-05T11:27:03-07:00" "fix: report Chase refunds as positive credits"
state c4; branch_commit fix/schwab-parens "2026-09-09T14:02:38-07:00" "fix: parse parenthesized Schwab amounts as negative"
state c5; at "2026-09-12T10:31:09-07:00"; commit "chore: release 0.9.0"
git tag -a v0.9.0 -m "ledgerline 0.9.0"
state c6; branch_commit feat/strip-card-numbers "2026-09-18T16:12:26-07:00" "feat: strip masked card numbers from descriptions"
unset GIT_AUTHOR_DATE GIT_COMMITTER_DATE

if ! diff -r -q -x .git . "$FINAL" >/dev/null; then
  diff -r -q -x .git . "$FINAL" >&2
  echo "setup: rebuilt history does not end at the fixture state" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  git status --porcelain >&2
  echo "setup: the last commit does not hold the fixture state" >&2
  exit 1
fi

git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main --tags 2>/dev/null
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
rm -rf "$FINAL"

# The same seven sessions, as native logs where Codex and Claude Code actually keep them (not a
# repository fixture): Codex rollout JSONL under $HOME/.codex/sessions/YYYY/MM/DD/, Claude Code
# project JSONL under $HOME/.claude/projects/<encoded-cwd>/. Timestamps are computed relative to
# setup time, inside the last two weeks, so an ordinary "recent sessions" pass finds them wherever
# this trial actually runs. A sha256 manifest (not a second, host-visible copy of each log) goes to
# $TRIAL_HARNESS/.setup-manifest.sha256 so check.py's native_logs_unchanged can tell whether the
# agent under test touched one of them.
python3 "$S/gen_native_logs.py" "$HOME" "$TRIAL_HARNESS" "$(pwd)"
