# Reference behavior (correct): adopts v8, grounding the call in how much v7 differs from itself
# across its nightly snapshots and the side-by-side run, and says why the every-cell bar does not fit. Its
# outcome line carries a "<" of its own, and it marks the v7 record as superseded.
set -e
cat > decisions/2026-10-01-prompt-v8.md <<'MD'
---
title: Switch the support prompt to v8
date: 2026-10-01
candidate: prompts/v8.md
incumbent: prompts/v7.md
outcome: adopt (v8's gap < v7's own run-to-run spread)
candidate_passes: 134/180
incumbent_passes: 138/180
---

## Context

v8 restates v7's policies in about a third fewer words (506 vs 746), to cut token cost and response latency. No policy changed.

## Evidence

Side-by-side run on 2026-09-30: v8 passed 134 of 180, v7 138 of 180. v8 is lower in 14 of the 36 scenario/model cells and higher in 12; the biggest single-cell drop is `customs-fees-international` on gpt-mini (5 to 1).

To see whether differences like these mean anything, I compared v7 with itself. The same prompt scored 136, 140 and 132 in the nightly snapshots of 09-09, 09-16 and 09-23, and 138 in the side-by-side run: a range of 8 passes with nothing changed. Any two of those four v7 runs disagree in 8 to 15 cells, with single-cell drops of up to 4 (`locked-account-identity` on gpt-mini went from 5 in the 09-09 nightly to 1 in the side-by-side run). Per model, v7's flash results ranged from 39 to 49; v8's 37 on flash is 6 below the side-by-side v7, while v7's own flash results differ by up to 10.

Every difference between v8 and v7 (the 4-pass total, the 14 lower cells, the 5-to-1 cell, flash) is the size v7 shows against itself. These results show no detectable difference. They cannot rule out a small drop of a few passes in 180, but a drop as large as v7's own night-to-night range would likely have shown.

## Decision

Adopt v8. On the "no worse in every cell" bar: v7 fails that bar against each of its own nightly runs (the 09-23 nightly is lower than the 09-09 one in 10 cells), so with 5 repeats per cell it would turn down any prompt, including an identical copy of v7. What we can honestly tell support leadership is that v8 shows no difference beyond what the same prompt shows from night to night.

## Follow-ups

Watch the next two weekly nightly snapshots on v8. If a total lands below 132 (the lowest v7 has scored in these runs) or flash stays below 39, run another side-by-side.
MD
printf '\nSuperseded by decisions/2026-10-01-prompt-v8.md.\n' >> decisions/2026-06-11-prompt-v7.md
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Decision: switch to v8. The record is in decisions/2026-10-01-prompt-v8.md.

v8 passed 134/180 against v7's 138/180 in the side-by-side run, and it is lower in 14 of 36 cells, including one that went 5 to 1. But v7 against itself looks the same: its four runs (three nightlies plus the side-by-side) scored 132 to 140, any two of them disagree in 8 to 15 cells, and single cells drop by up to 4 between them. Nothing v8 shows is outside that, so there is no detectable difference, and the shorter prompt saves tokens and latency.

I didn't apply the every-cell bar as stated: v7 fails it against its own nightly runs, so it would reject any prompt, even an identical one. I suggested wording for leadership in the record, plus a nightly check for the next two weeks.
MSG
