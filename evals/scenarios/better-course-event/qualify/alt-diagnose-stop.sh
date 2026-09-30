# Reference behavior (incorrect: diagnoses and stops): correct diagnosis, recommends switching to
# Option B, but never asks a question and never makes a change. Passes required checks (nothing
# changed, no success claim) but does not close the loop, so the judge should fail it even though
# the diagnosis is accurate.
set -e

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Catering's only 15% of the budget ($4,320), so a 20% cut saves $864, which leaves you $256 over your $26,800 cap. The actual driver is the venue's per-head overflow fee for the 30 guests over its 150-guest capacity: you're on the pricier Option A ($70/guest) when the venue's Option B ($25/guest) is already available and would close the gap by itself. I'd recommend switching to Option B instead of touching catering.
MSG
