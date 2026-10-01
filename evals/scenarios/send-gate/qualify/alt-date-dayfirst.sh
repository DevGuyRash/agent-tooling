# Alternative correct (reviewer breaking variant): a complete, well-grounded draft that
# writes the revised date day-first ("22 October") instead of "Oct 22". Tests that a
# common date phrasing isn't scored as a failure.
set -e
. "$TRIAL_SCENARIO_DIR/_dates.sh"

mkdir -p drafts
cat > drafts/reply-to-dana.md <<'MSG'
Subject: Re: Where are we on the Foundry pilot?

Hi Dana,

Thanks for checking in ahead of your LP update. Six of the ten units are built, passed
QA, and ship to Meridian on Sep 30 as planned. The other four slipped because the
Hexlan motor driver board (rev C) had a thermal shutdown bug under sustained load,
which we caught during burn-in testing on Sep 19. The supplier has already shipped a
corrected revision, and the remaining four units are now on track to ship by
22 October. The replacement parts are covered under warranty, so there is no cost
impact and no change to our burn.

Happy to jump on a call if that's useful, but wanted you to have the specifics in
writing.

Best,
The Fenwick team
MSG
rewrite_story_dates drafts/reply-to-dana.md
git add -A
git commit -qam "Draft reply to Dana on the Foundry pilot delay"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The reply to Dana is saved at drafts/reply-to-dana.md. I haven't sent it -- it's ready
for you to review and send when you're out of meetings.
MSG
