# outside-image with the Dockerfile copying the new package too: the image holds supportcal/, so it passes.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/outside-image.sh"
sed -i 's#^COPY deskd/ deskd/$#COPY deskd/ deskd/\nCOPY supportcal/ supportcal/#' Dockerfile
grep -q '^COPY supportcal/ supportcal/$' Dockerfile
git add -A
git commit -q -m "Dockerfile: copy supportcal"
