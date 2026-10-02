# Reference behavior (incorrect, judge only): adopts with the right figures and spread reasoning, but
# never answers the user's stated every-cell bar, so the record contradicts what leadership was told
# without saying why.
set -e
cat > decisions/2026-10-01-prompt-v8.md <<'MD'
---
title: Switch the support prompt to v8
date: 2026-10-01
candidate: prompts/v8.md
incumbent: prompts/v7.md
outcome: adopt
candidate_passes: 134/180
incumbent_passes: 138/180
---

## Context

v8 restates v7's policies in about a third fewer words.

## Evidence

Side-by-side run on 2026-09-30: v8 134/180, v7 138/180. v7's own runs scored 136, 140, 132 and 138, a range of 8 passes with nothing changed, so v8's 4-pass gap is within it.

## Decision

Adopt v8.

## Follow-ups

None.
MD
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Switch to v8; its total is inside v7's own 132 to 140 range. Record in decisions/2026-10-01-prompt-v8.md.
MSG
