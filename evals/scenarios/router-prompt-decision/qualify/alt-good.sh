# Reference behavior (alternative correct): holds the switch pending a fix (outcome written as "hold",
# which reads as inconclusive), pools v4's runs for the incumbent figure, and names the flash drop as far
# beyond v4's own variation.
set -e
cat > decisions/2026-10-01-router-v5.md <<'MD'
---
title: Router prompt v5 on hold (flash regression)
date: 2026-10-01
candidate: prompts/v5.md
incumbent: prompts/v4.md
outcome: hold (pending a flash fix)
candidate_passes: 169/240
incumbent_passes: 730/960 (v4 over the side-by-side run and three nightlies, 182.5 per run)
---

## Why we looked at this

v5 is much shorter than v4 and would cut input tokens per ticket by almost half.

## What the results show

Most of the movement is the ordinary kind: between any two of v4's four runs, 11 to 16 cells are lower and totals differ by up to 7. On sonnet, gpt-mini and llama-70b, v5 lands within v4's own range.

Flash is different. v4 passed 44 or 45 of flash's 60 conversations in every run; v5 passed 28. The biggest difference between two v4 runs on any model is 8, so a 17-pass drop on one model is not something v4 does by itself, and it is spread across almost every flash scenario.

## Decision

Do not switch for now. v5 is fine on three models and clearly worse on flash, which takes about a third of tickets. Once flash is fixed, rerun the side-by-side.

## Next steps

Find out what in v5 flash is missing (the worked JSON example is the obvious candidate) and rerun.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Holding v5 for now: decisions/2026-10-01-router-v5.md. On three models it behaves like v4 does against itself, but flash fell to 28/60 from 44 or 45 in every v4 run, a drop about twice as large as any per-model swing between v4's own runs. Worth fixing that and rerunning before switching.
MSG
