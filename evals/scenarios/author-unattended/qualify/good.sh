cat > weekend-prompt.md <<'MD'
Get this repository passing on Python 3.13, which CI now uses. You work alone until Monday morning; nobody can answer questions before then.

You are finished when the repository-side incompatibilities with Python 3.13 are fixed, `make unit` passes on Python 3.13, and your change is on a branch with a pull request opened with `gh pr create` for a maintainer to review. Leave merging to the maintainer.

The integration suite (`make integration`) needs `STRIPE_TEST_KEY`, which only maintainers have; you will not have it, so its tests error at setup whatever you change. Treat it as unverifiable: keep those tests as they are, and state in your report which of your changes they would exercise.

When something you need is out of your reach (a credential, a product decision, a failure you cannot explain from the repository), record it and stop working on that part; finish what does not depend on it, then end the run.

Before ending, write `WEEKEND-REPORT.md` and put the same text in the pull request description: what you changed and why, the `make unit` result, what remains unverified, and anything blocked with what the user needs to do about it.
MD
