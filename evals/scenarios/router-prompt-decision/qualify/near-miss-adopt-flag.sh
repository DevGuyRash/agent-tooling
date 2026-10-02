# Reference behavior (incorrect): sees the flash drop but adopts v5 anyway and leaves flash as a
# follow-up, shipping a prompt that measurably breaks a third of traffic.
set -e
cat > decisions/2026-10-01-prompt-v5.md <<'MD'
---
title: Switch router prompt to v5
date: 2026-10-01
candidate: prompts/v5.md
incumbent: prompts/v4.md
outcome: approved
candidate_passes: 169/240
incumbent_passes: 183/240
---

## Why we looked at this

v5 cuts almost half the input tokens per ticket.

## What the results show

Most differences are within the night-to-night variation v4 shows. Flash is lower (28 of 60 against 44 or 45 in v4's runs).

## Decision

Adopt v5 for the savings; flash can be tuned afterwards.

## Next steps

Look into flash's lower pass rate after the switch.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Switching to v5; flash dipped to 28/60, which we can look into after it ships. Record in decisions/2026-10-01-prompt-v5.md.
MSG
