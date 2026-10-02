# Reference behavior (correct): rejects v5 because flash falls far below every v4 run, a drop much
# larger than anything v4's own runs show, while the other models are within v4's spread.
set -e
cat > decisions/2026-10-01-prompt-v5.md <<'MD'
---
title: Keep router prompt v4; v5 regresses on flash
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

Side-by-side run on 2026-09-30: v5 passed 169 of 240, v4 183 of 240.

To tell real differences from night-to-night movement, I compared v4 with itself first. Its four runs (nightlies of 09-09, 09-16, 09-23 and the side-by-side) scored 184, 185, 178 and 183, so two v4 runs differ by up to 7 in total, and by up to 8 on any one model (sonnet went 46 to 54 between two nightlies). Individual cells move by up to 4 between v4 runs, so single cells tell us little.

Against that:

- flash: v5 passed 28 of 60. v4 scored 44, 45, 45 and 45 on flash in its four runs. A drop of 17 against the side-by-side v4 is more than twice the largest per-model difference between any two v4 runs, and v5 is lower on 11 of flash's 12 scenarios. No single flash cell drops by more than 2, which is why it doesn't stand out cell by cell.
- sonnet (53), gpt-mini (48), llama-70b (40): all inside or at the edge of v4's own range on those models.
- total: 169 is 9 below v4's lowest run (178), and the whole shortfall comes from flash.

## Decision

Reject v5 as it stands. The cell-level movement elsewhere is the kind v4 shows against itself, but the flash drop is not: it is far outside anything v4's runs show, and about a third of tickets go to flash. A plausible cause is that v5 drops v4's worked example of the JSON reply, which the smaller model may rely on.

## Next steps

Try v5 with the worked example restored and rerun the side-by-side; adopt if flash comes back within v4's range.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I wouldn't switch yet: v5 is clearly worse on flash. Flash passed 28/60 under v5, while v4 scored 44 or 45 of 60 on flash in all four of its runs. That 17-point drop is more than twice the largest per-model swing between any two v4 runs (8), and it shows up across 11 of flash's 12 scenarios, so it isn't night-to-night noise even though no single cell moves by more than 2. The other three models look like v4 against itself. Since about a third of tickets go to flash, I recorded it as rejected in decisions/2026-10-01-prompt-v5.md, with a suggestion to restore the worked JSON example and rerun.
MSG
