# Reference behavior (incorrect): the right call on flash, but the pass totals are miscounted.
set -e
cat > decisions/2026-10-01-prompt-v5.md <<'MD'
---
title: Keep router prompt v4; v5 regresses on flash
date: 2026-10-01
candidate: prompts/v5.md
incumbent: prompts/v4.md
outcome: reject
candidate_passes: 179/240
incumbent_passes: 183/240
---

## Why we looked at this

v5 is a terser rewrite of v4.

## What the results show

v5 passed 179 of 240 against v4's 183. Flash fell to 28 of 60, against 44 or 45 in every v4 run, a drop well beyond the largest per-model difference between two v4 runs (8).

## Decision

Reject v5 as it stands because of flash.

## Next steps

Fix flash and rerun.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Not switching: flash fell to 28/60 from 44-45 in every v4 run, far beyond v4's own variation, even though the totals are close (179 vs 183). Record in decisions/2026-10-01-prompt-v5.md.
MSG
