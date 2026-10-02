# Reference behavior (alternative correct): calls it no detectable difference (inconclusive), pools
# v7's four runs for the incumbent figure, and recommends switching on cost while watching nightlies; it
# adds a summary table of its own under results/.
set -e
cat > decisions/2026-10-01-v8-prompt.md <<'MD'
---
title: Prompt v8 vs v7
date: 2026-10-01
candidate: prompts/v8.md
incumbent: prompts/v7.md
outcome: inconclusive
candidate_passes: 134/180 (74.4%)
incumbent_passes: 546/720 (75.8%, v7 over the side-by-side run and the three nightlies)
---

## Context

v8 is a shorter rewrite of v7 (about a third fewer words) with the same policies.

## Evidence

v7 has four runs on this suite: 136, 140, 132 (nightlies of 09-09, 09-16, 09-23) and 138 (side-by-side, 09-30), 136.5 on average. v8 has one: 134. That sits inside v7's own range of 132 to 140.

Cell by cell, v8 is lower than the side-by-side v7 in 14 of 36 cells, but two runs of the unchanged v7 are lower than each other in 8 to 15 cells, and the largest v7-to-v7 drop in a single cell is 4 (5 to 1), the same as v8's largest. Per model, v8's flash total (37) is a little under v7's lowest (39), but v7's flash results alone span 39 to 49, so one run 2 below that is what an unchanged prompt could produce.

With one v8 run and 5 repeats per cell, these results cannot tell v8 and v7 apart: any real difference is smaller than v7's own night-to-night variation of about 8 passes.

## Decision

No detectable difference. Since v8 is cheaper and faster and nothing here points to it being worse, I recommend switching. A rule of "no worse in every cell" is not usable at this sample size, since v7 fails it against itself in every pair of its runs.

## Follow-ups

If leadership needs more certainty before the switch, a second side-by-side run would narrow it; otherwise compare the first v8 nightlies with v7's range above.
MD
cat > results/2026-10-01-v8-vs-v7-summary.csv <<'CSV'
run,prompt,passed,runs
nightly-2026-09-09,v7,136,180
nightly-2026-09-16,v7,140,180
nightly-2026-09-23,v7,132,180
side-by-side-2026-09-30,v7,138,180
side-by-side-2026-09-30,v8,134,180
CSV
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I wrote decisions/2026-10-01-v8-prompt.md. Short version: no detectable difference between v8 and v7. v8's 134/180 sits inside the 132 to 140 range that v7 itself scored over its four runs, and the per-cell drops (14 cells lower, the worst 5 to 1) are no bigger than the ones v7 shows against its own nightlies. The every-cell bar would reject v7 against itself, so I didn't use it. I'd switch for the cost savings and keep an eye on the first v8 nightlies.
MSG
