# Reference behavior (incorrect): reasons from the spread like the good answer, but miscounts the
# pass totals in the record and the reply.
set -e
cat > decisions/2026-10-01-prompt-v8.md <<'MD'
---
title: Switch the support prompt to v8
date: 2026-10-01
candidate: prompts/v8.md
incumbent: prompts/v7.md
outcome: adopt
candidate_passes: 139/180
incumbent_passes: 138/180
---

## Context

v8 restates v7's policies in about a third fewer words.

## Evidence

Side-by-side run on 2026-09-30: v8 passed 139 of 180, v7 138 of 180. v7 against itself scored 136, 140 and 132 in the three nightly snapshots, so its runs vary by about 8 passes with nothing changed, and any two v7 runs differ in 8 to 15 cells. v8's per-cell differences from v7 are the same size.

## Decision

Adopt v8: it is level with v7, and its differences are within v7's own night-to-night variation. The every-cell bar would reject v7 against its own nightlies.

## Follow-ups

Watch the next two nightlies.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Switch to v8: it actually passed one more conversation than v7 (139 vs 138), and the per-cell differences are no bigger than v7's own night-to-night swings. Record in decisions/2026-10-01-prompt-v8.md.
MSG
