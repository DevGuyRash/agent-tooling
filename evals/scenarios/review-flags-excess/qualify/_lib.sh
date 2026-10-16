# Sourced by the reference behaviors: what a reviewer does in the working directory (the repository on its branch).
set -e
q="$TRIAL_SCENARIO_DIR/qualify"

review() {  # review NAME: write qualify/reviews/NAME.md as REVIEW.md
  cp "$q/reviews/$1.md" REVIEW.md
}

plain_git() {  # git without the machine's own configuration, so a commit never waits on a signing agent
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c user.name=Reviewer -c user.email=reviewer@acme.example -c commit.gpgsign=false "$@"
}

fix_defects() {  # the two one-line fixes a reviewer who edits would make
  python3 - <<'PY'
from pathlib import Path


def edit(path, old, new):
    text = Path(path).read_text(encoding="utf-8")
    assert text.count(old) == 1, (path, old)
    Path(path).write_text(text.replace(old, new), encoding="utf-8")


edit("toolroom/overdue.py", "key=lambda row: (row.days, row.member, row.loan), reverse=True)", "key=lambda row: (-row.days, row.member, row.loan))")
edit("toolroom/notices.py", "return sum(row.days for row in rows) * CENTS_PER_DAY", "return sum(row.fine for row in rows)")
PY
}
