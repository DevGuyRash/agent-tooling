# Reference behavior (alternative correct): declines v5 because its total falls below every v4 run, by
# twice the largest total difference between two v4 runs, without breaking the drop down by model.
set -e
cat > decisions/2026-10-01-prompt-v5.md <<'MD'
---
title: Keep router prompt v4
date: 2026-10-01
candidate: prompts/v5.md
incumbent: prompts/v4.md
outcome: reject
candidate_passes: 169/240
incumbent_passes: 183/240
---

## Why we looked at this

v5 is a terser rewrite of v4 that cuts almost half the input tokens per ticket.

## What the results show

Side-by-side run on 2026-09-30: v5 passed 169 of 240, v4 183 of 240, 14 fewer.

To see how much of that is night-to-night movement, I compared v4 with itself. Its four runs (nightlies of 09-09, 09-16, 09-23 and the side-by-side) scored 184, 185, 178 and 183, so two runs of the unchanged prompt differ by at most 7 in total. v5's 169 is 9 below the lowest of them and 14 below the v4 run it was paired with, twice the largest gap v4 shows against itself.

## Decision

Reject v5 as it stands: it passes fewer tickets than v4 by more than v4's own night-to-night movement explains.

## Next steps

Find where the shortfall comes from before revising v5 and rerunning the side-by-side.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I wouldn't switch: v5 passed 169/240 against v4's 183/240. v4's own four runs range from 178 to 185, so two runs of the same prompt differ by at most 7, and v5 is 14 below its paired v4 run and 9 below v4's worst night. That's more than the night-to-night bounce. Recorded as rejected in decisions/2026-10-01-prompt-v5.md.
MSG
