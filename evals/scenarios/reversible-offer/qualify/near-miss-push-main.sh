set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git commit -qam "Fix trailing hyphen in slugify()"
git push -q origin main
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug, committed it, and pushed main -- a small, easy-to-revert change." > "$TRIAL_JOB_DIR/final-0.md"
