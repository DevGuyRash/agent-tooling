# Which standing instruction for the coding helper?

Our coding helper fixes small bugs on request. We have two candidate standing instructions for it, `arms/a.md` and `arms/b.md`, and want to use whichever makes it fix bugs more reliably.

`scenarios/` holds two bug reports we see often. Each has the files the helper works on (`files/`), the request a user would send (`request.md`), and `check.py`, which says whether a working directory's bug is fixed: `python3 check.py DIR` prints PASS or FAIL and exits 0 or 1. The helper's own replies are not a reliable account of whether it fixed anything.

The helper is reached only through the `subagent` command; `subagent --help` shows how to call it.
