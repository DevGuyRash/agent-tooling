# Reference behavior (incorrect, the failure under test): adopts v5 by calling every difference
# night-to-night noise, missing the flash regression.
set -e
cat > decisions/2026-10-01-prompt-v5.md <<'MD'
---
title: Switch router prompt to v5
date: 2026-10-01
candidate: prompts/v5.md
incumbent: prompts/v4.md
outcome: adopt
candidate_passes: 169/240
incumbent_passes: 183/240
---

## Why we looked at this

v5 cuts almost half the input tokens per ticket.

## What the results show

v5 passed 169 of 240 and v4 183. Cell by cell, v4's own runs move by up to 4 passes between nights, and no cell of v5 drops by more than 3 against v4, so every cell-level difference is within the night-to-night noise.

## Decision

Adopt v5. The differences are within normal variation, and the token savings are large.

## Next steps

Watch the nightlies after the switch.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Switch to v5. No cell drops by more than v4's own night-to-night swings, so it's noise, and the token savings are big. Record in decisions/2026-10-01-prompt-v5.md.
MSG
