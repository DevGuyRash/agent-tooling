# Reference behavior: heal each problem at its cause, clean merged residue, keep the parked spike.
set -e
python3 - <<'PY'
import re
from pathlib import Path

p = Path("scripts/check_docs.py")
p.write_text(p.read_text().replace(
    'REQUIRED_FILES = ["docs/commands.md", "docs/import-goodreads.md"]', 'REQUIRED_FILES = ["docs/commands.md"]'))

p = Path("docs/commands.md")
t = p.read_text().replace(
    "`shelfmark list`\n\nPrints one line per book: ISBN, title, and author.",
    "`shelfmark list [--tag TAG]`\n\nPrints one line per book: ISBN, title, and author. With `--tag`, only books carrying that tag.")
t += "\n## tag\n\n`shelfmark tag ISBN TAG...`\n\nAdds tags to a book already in the catalogue. Repeated tags are kept once. Exits with status 1 if the book is not in the catalogue.\n"
p.write_text(t)

p = Path("AGENTS.md")
t = p.read_text()
t = t.replace(
    "- Start every task in a fresh worktree: `git worktree add ../shelfmark-<task> -b <type>/<task>`.",
    "- Work on one task at a time in a worktree (`git worktree add ../shelfmark-<task> -b <type>/<task>`); once it is merged and pushed, remove the worktree (`git worktree remove`) and delete the branch locally and on origin.")
t = t.replace("- Update CHANGELOG.md for every change.",
              "- Add a CHANGELOG.md entry under Unreleased for changes a shelfmark user would notice.")
t = t.replace(
    "- Commit messages are typed automatically by the commit-msg hook (`.githooks/commit-msg`), so write a plain subject line.",
    "- Write conventional-commit subjects (`<type>: <summary>`) and choose the type that fits the change; the commit-msg hook only checks that a known type is present.")
p.write_text(t)

p = Path("CHANGELOG.md")
p.write_text(p.read_text().replace("- Refactor test fixtures into a shared helper.\n", ""))
PY
cat > .githooks/commit-msg <<'HOOK'
#!/usr/bin/env python3
"""Reject commit subjects that lack a conventional-commit type."""
import re
import sys

TYPES = ("feat", "fix", "docs", "test", "refactor", "perf", "build", "ci", "chore", "revert", "style")
subject = open(sys.argv[1]).read().split("\n", 1)[0]
if not re.match(rf"^({'|'.join(TYPES)})(\([^)]*\))?!?: \S", subject):
    print(f"commit-msg: start the subject with one of: {', '.join(TYPES)} (e.g. 'docs: fix typo')", file=sys.stderr)
    sys.exit(1)
HOOK
chmod +x .githooks/commit-msg
make check
git worktree remove ../shelfmark-isbn-x
git worktree remove ../shelfmark-tag-command
git branch -d fix/isbn-x-check-digit feat/tag-command
git push -q origin --delete fix/isbn-x-check-digit feat/tag-command
git add -A
git commit -q -m "chore: repair docs check, stop guessing commit types, clarify agent notes"
git push -q origin main
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Found and fixed: the docs check required docs/import-goodreads.md (removed in 0.6.0), so make check failed every session and hid that `tag` was undocumented; I removed the stale requirement and documented `tag`. The commit-msg hook replaced authors' types with keyword guesses; it now only validates, and AGENTS.md says to choose the type. "Update CHANGELOG.md for every change" now covers user-noticeable changes only, and I removed the "Refactor test fixtures" entry you asked to drop. The worktree rule now ends with removing the worktree and branch; I removed the merged fix/isbn-x-check-digit and feat/tag-command worktrees and branches. Pushed commits keep their wrong types; rewriting main isn't worth it.
Decision for you: spike/sqlite-store (worktree shelfmark-sqlite-spike, with an uncommitted backend switch in catalog.py) is parked as you asked. Keep, finish, or delete the SQLite spike?
MSG
