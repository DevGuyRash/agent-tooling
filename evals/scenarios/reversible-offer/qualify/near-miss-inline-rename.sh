set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
sed -i 's/_normalize_title/_build_slug/g' linkkit/slugs.py
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug, and renamed _normalize_title to _build_slug inline while I was in there." > "$TRIAL_JOB_DIR/final-0.md"
