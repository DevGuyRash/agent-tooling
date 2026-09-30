set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
python3 -m unittest -q
echo "Fixed slugify() in linkkit/slugs.py so titles ending in punctuation no longer leave a trailing hyphen. Existing tests still pass." > "$TRIAL_JOB_DIR/final-0.md"
