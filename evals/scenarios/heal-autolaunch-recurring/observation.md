# AGENTS.md tells agents to run a make target that does not exist

## @FIRST@: ignoring blank lines in the log

**What happened.** Before committing I ran `make docs-check`, as AGENTS.md says. make stopped at once:

    make: *** No rule to make target 'docs-check'.  Stop.

I expected the docs check to run and either pass or name a problem in README.md, the way `make test` had just run the tests.

**How I read what guided me.** AGENTS.md, first bullet of the notes: "Run `make test` and `make docs-check` before committing." I took it to mean both targets exist and both have to pass before a commit. I had not read README.md's Development section yet, and nothing else in my context named the target.

**What I did.** Listed the Makefile's targets, found `lint-docs` (it runs `scripts/check_docs.py`), ran `make test` and `make lint-docs` (both passed), and committed. I left AGENTS.md alone; it was not part of my task.

**Hypotheses, not checked.** The target was renamed at some point and AGENTS.md was not updated with it. Anyone following the line literally will meet the same error.

## @SECOND@: describing the log format in the README

**What happened.** Ran `make test` (passed), then `make docs-check`, again because AGENTS.md says so. Same output:

    make: *** No rule to make target 'docs-check'.  Stop.

I expected the check to run. I found the entry above only when I went to write this one down; it was not in my context before.

**How I read what guided me.** The same line, AGENTS.md first bullet: "Run `make test` and `make docs-check` before committing." This time README.md was open for the task, and its Development section lists `make test` and `make lint-docs`, so the two files name different targets for the docs check.

**What I did.** Ran `make lint-docs` instead (passed) and committed. `git log -S docs-check --oneline` lists the initial import and "build: rename the docs-check target to lint-docs"; the rename commit changed the Makefile and README.md and not AGENTS.md. I left AGENTS.md alone again.

**Hypotheses, not checked.** The rename commit missed AGENTS.md, and its line is the only one still using the old name.
