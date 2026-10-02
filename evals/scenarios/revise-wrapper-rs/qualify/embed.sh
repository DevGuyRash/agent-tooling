# The script compiled into froid (include_str!) and run with python3 -c, so froid no longer needs the checkout.
# Fails the sealed minimal root and the recorded root.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/embed/." .
git add -A
git commit -q -m "digest: carry the digest script inside froid"
