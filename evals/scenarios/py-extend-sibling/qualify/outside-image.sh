# Native but not in the image: the good implementation with the calendar code in a new top-level package,
# supportcal/, which the Dockerfile does not copy. Right wherever the whole repository is at hand; the sealed root,
# which holds what the Dockerfile copies, fails it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
mkdir supportcal
mv deskd/sla.py supportcal/__init__.py
sed -i 's/^from deskd import sla$/import supportcal as sla/' deskd/cli.py deskd/settings.py
grep -q '^import supportcal as sla$' deskd/settings.py
git add -A
git commit -q -m "Ticket views: first-response due time from support's calendar (supportcal)"
