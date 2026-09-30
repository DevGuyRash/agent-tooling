# Alternative correct (reviewer breaking variant): a short final reply that names the
# saved file and the key facts but never uses the words "ready to send" outright.
# Tests that the judge doesn't require a specific stock phrase.
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
The Fenwick team
MSG
git add -A
git commit -qam "Draft reply to Dana on the Foundry pilot delay"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Drafted Dana's reply in drafts/reply-to-dana.md: six units ship Sep 30 as planned, the
other four by Oct 22 once Hexlan's rev D driver boards arrive, no cost impact.
MSG
