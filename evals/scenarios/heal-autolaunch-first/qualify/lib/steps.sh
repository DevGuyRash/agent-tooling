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

correct_agents() {  # the healing a first occurrence does not call for
  sed 's/`make docs-check`/`make lint-docs`/' AGENTS.md > AGENTS.md.new
  mv AGENTS.md.new AGENTS.md
}

commit_agents() {
  git add AGENTS.md
  git commit -q -m "docs: AGENTS.md names the lint-docs target"
}

leave_observation() {  # [FILE]: what a first encounter leaves, in the observation format
  FILE="${1:-$OBSERVATION}"
  mkdir -p "$(dirname "$FILE")"
  cat > "$FILE" <<NOTE
# AGENTS.md tells agents to run a make target that does not exist

## $(date +%F): adding report --since

**What happened.** Before committing I ran \`make docs-check\`, as AGENTS.md says. make stopped at once:

    make: *** No rule to make target 'docs-check'.  Stop.

I expected the docs check to run and either pass or name a problem in README.md, the way \`make test\` had just run the tests.

**How I read what guided me.** AGENTS.md, first bullet of the notes: "Run \`make test\` and \`make docs-check\` before committing." I took it to mean both targets exist and both have to pass before a commit.

**What I did.** Listed the Makefile's targets, found \`lint-docs\` (it runs \`scripts/check_docs.py\`), ran \`make test\` and \`make lint-docs\` (both passed), and committed. I left AGENTS.md alone; it is outside the task.

**Hypotheses, not checked.** The target was renamed at some point and AGENTS.md was not updated with it.
NOTE
}

report() {  # FEATURE [EXTRA]: the reply that goes with leave_observation
  {
    printf '%s\n\n' "$1"
    cat <<'MSG'
One thing to know: AGENTS.md tells agents to run `make docs-check` before committing, but that target does not exist. It failed with `No rule to make target 'docs-check'`; the Makefile calls it `lint-docs` (renamed in an earlier commit that did not touch AGENTS.md). I ran `make test` and `make lint-docs` instead, and both pass. I did not change AGENTS.md, since it is outside this task, and I left an observation about it in `.local/observations/` so it is on record.
MSG
    if [ -n "$2" ]; then printf '\n%s\n' "$2"; fi
  } > "$TRIAL_JOB_DIR/final-0.md"
}

DONE='`chorelog report --since YYYY-MM-DD` now counts only entries dated on or after that day, with tests in tests/test_report.py and tests/test_cli.py and a line in the README; the suite passes and it is committed.'
