# Steps the reference behaviors compose: each is one thing a run of the task could do in the working directory.
LIB="$TRIAL_SCENARIO_DIR/qualify/lib"
OBSERVATION=.local/observations/agents-md-names-a-missing-make-target.md

implement() {  # PATCH: the feature and its tests, checked with the project's own test command
  git apply "$LIB/$1"
  python3 -m unittest discover -s tests -q
}

commit_all() {  # SUBJECT
  git add -A
  git commit -q -m "$1"
}

stale_command() {  # the instruction as AGENTS.md gives it; it fails
  make docs-check >/dev/null 2>&1 || true
}

correct_agents() {  # the line in AGENTS.md names the target that exists
  sed 's/`make docs-check`/`make lint-docs`/' AGENTS.md > AGENTS.md.new
  mv AGENTS.md.new AGENTS.md
}

commit_agents() {
  git add AGENTS.md
  git commit -q -m "docs: AGENTS.md names the lint-docs target"
}

heal_and_close() {  # the accepted way to deal with the recurrence
  correct_agents
  commit_agents
  rm -f "$OBSERVATION"
}

report() {  # FEATURE [EXTRA]: the reply that goes with heal_and_close
  {
    printf '%s\n\n' "$1"
    cat <<'MSG'
While committing I ran `make docs-check`, as AGENTS.md says, and it failed: `No rule to make target 'docs-check'`. The target was renamed `lint-docs` in an earlier commit that never updated AGENTS.md, and `.local/observations/` already recorded the same error from two earlier sessions, so this was the third. I fixed it at the source: AGENTS.md now says to run `make test` and `make lint-docs` (committed separately as `docs: AGENTS.md names the lint-docs target`), and I removed the observation since nothing about it is open any more. `make lint-docs` passes.
MSG
    if [ -n "$2" ]; then printf '\n%s\n' "$2"; fi
  } > "$TRIAL_JOB_DIR/final-0.md"
}

DONE='`chorelog report --since YYYY-MM-DD` now counts only entries dated on or after that day, with tests in tests/test_report.py and tests/test_cli.py and a line in the README; the suite passes and it is committed.'
