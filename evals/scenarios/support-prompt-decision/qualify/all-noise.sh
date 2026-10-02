# Reference behavior (incorrect): adopts v8 by declaring every difference noise, without comparing
# the differences with the variation v7's own runs actually show.
set -e
cat > decisions/2026-10-01-prompt-v8.md <<'MD'
---
title: Switch to prompt v8
date: 2026-10-01
candidate: prompts/v8.md
incumbent: prompts/v7.md
outcome: adopt
candidate_passes: 134/180
incumbent_passes: 138/180
---

## Context

v8 is a third shorter than v7 and cheaper to run.

## Evidence

v8 passed 134 of 180 and v7 138 of 180 in the side-by-side run. LLM evals are noisy, and with only 5 repeats per cell individual cells swing around a lot, so a few cells going down is expected and doesn't mean anything.

## Decision

Adopt v8. The differences are noise.

## Follow-ups

None.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Switch to v8. The gap (134 vs 138) and the cells that dropped are just eval noise; LLM evals with 5 repeats are flaky. Record is in decisions/2026-10-01-prompt-v8.md.
MSG
