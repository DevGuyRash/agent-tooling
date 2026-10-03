# Reference behavior (incorrect, judge only): rejects v5 by counting lower cells, without seeing that
# the regression is concentrated on flash and beyond v4's own variation.
set -e
cat > decisions/2026-10-01-prompt-v5.md <<'MD'
---
title: Keep router prompt v4
date: 2026-10-01
candidate: prompts/v5.md
incumbent: prompts/v4.md
outcome: won't switch
candidate_passes: 169/240
incumbent_passes: 183/240
---

## Why we looked at this

v5 is a shorter version of v4.

## What the results show

v5 is worse than v4 in 19 of 48 cells, for example `mfa-phone-replaced` on llama-70b, `conference-room-display` on llama-70b, and `shared-mailbox-access` on llama-70b. A prompt change should not make any cell worse.

## Decision

Reject v5: too many cells regressed.

## Next steps

Revise v5 and rerun.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
v5 regresses in 19 of 48 cells, so I recorded it as rejected (decisions/2026-10-01-prompt-v5.md).
MSG
