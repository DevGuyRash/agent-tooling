# tessellate-review-bot

Instructions for the PR review bot, and the trial harness we use to test changes to them.

- `instructions/current.md` — what the bot runs today.
- `instructions/candidate.md` — proposed replacement.
- `trial/design.md` — the planned trial comparing the two.
- `history/` — earlier harness runs.

Trials run in CI (`trial` workflow) and upload `results.csv` as an artifact. Whoever kicks one off downloads it and runs the trial's decision script from the repository root.
