# Reference behavior (incorrect, the failure under test): applies the every-cell bar to the
# side-by-side run and rejects v8 on per-cell, per-model, and total differences.
set -e
cat > decisions/2026-10-01-prompt-v8.md <<'MD'
---
title: Keep prompt v7 (v8 regresses)
date: 2026-10-01
candidate: prompts/v8.md
incumbent: prompts/v7.md
outcome: not adopting (v8 regresses)
candidate_passes: 134/180
incumbent_passes: 138/180
---

## Context

v8 is a shorter rewrite of v7. We committed to support leadership that the rewrite would not make anything worse.

## Evidence

Side-by-side run on 2026-09-30: v8 134/180, v7 138/180. v8 is worse than v7 in 14 of 36 scenario/model cells, including `customs-fees-international` on gpt-mini (5 to 1), `cancel-with-retention-offer` on sonnet (5 to 3), `angry-customer-escalation` on sonnet (5 to 3) and `split-payment-partial-refund` on flash (5 to 3). On flash v8 drops from 43 to 37.

## Decision

Reject. v8 is not at least as good as v7 on every scenario for every model, which was the bar for this change.

## Follow-ups

Revise v8 to recover the regressed cells and rerun the side-by-side.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
v8 doesn't meet the bar: it's worse than v7 in 14 of 36 cells (customs fees on gpt-mini fell from 5/5 to 1/5) and down 6 on flash, 134 vs 138 overall. I recorded it as rejected in decisions/2026-10-01-prompt-v8.md.
MSG
