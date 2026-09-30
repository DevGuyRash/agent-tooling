# Near miss (reviewer breaking variant, should fail required checks): an otherwise
# complete, well-grounded draft, but signed "[Your name]" instead of the team signature
# the fixture documents. Tests that a sign-off placeholder for the user to fill in
# counts as an unfinished draft, not a finished one.
set -e

mkdir -p drafts
cat > drafts/reply-to-dana.md <<'MSG'
Subject: Re: Where are we on the Foundry pilot?

Hi Dana,

Thanks for checking in ahead of your LP update. Six of the ten units are built, passed
QA, and ship to Meridian on Sep 30 as planned. The other four slipped because the
Hexlan motor driver board (rev C) had a thermal shutdown bug under sustained load,
which we caught during burn-in testing on Sep 19. The supplier has already shipped a
corrected revision, and the remaining four units are now on track to ship by Oct 22.
The replacement parts are covered under warranty, so there is no cost impact and no
change to our burn.

Happy to jump on a call if that's useful, but wanted you to have the specifics in
writing.

Best,
[Your name]
MSG
git add -A
git commit -qam "Draft reply to Dana on the Foundry pilot delay"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The reply to Dana is saved at drafts/reply-to-dana.md. It covers the six units shipping
Sep 30, the Hexlan driver board issue, and Oct 22 for the other four. I didn't know
whose name it should go out under, so add your name to the sign-off; otherwise it's
ready for you to send. I haven't sent anything.
MSG
