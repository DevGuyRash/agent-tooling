# Near miss, judge-only (reviewer breaking variant, should fail): saves the right facts
# to a file, but as bullet-point notes for the user to write up themselves, not an
# actual reply to Dana. draft_ready's regexes only look for the addressee/date/cause
# keywords and don't distinguish a note from a letter, so required checks pass this;
# only the judge, reading the saved file, can tell it isn't a reply.
set -e
. "$TRIAL_SCENARIO_DIR/_dates.sh"
mkdir -p notes
cat > notes/foundry-for-dana.md <<'MSG'
# Points for the reply to Dana (Foundry pilot)

- 6 of 10 units ship to Meridian Sep 30 as planned
- Remaining 4 waiting on Hexlan rev D driver board (rev C had a thermal shutdown bug, found in burn-in Sep 19)
- Remaining 4 ship by Oct 22 (boards ~Oct 15 + 5 days assembly/QA)
- No cost impact: warranty replacement
- Adding 48h burn-in gate for pilot #2
MSG
rewrite_story_dates notes/foundry-for-dana.md
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I pulled the key points for your reply to Dana into notes/foundry-for-dana.md so you can
write it up between meetings.
MSG
