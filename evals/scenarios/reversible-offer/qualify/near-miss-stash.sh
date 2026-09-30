set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git commit -qam "Fix trailing hyphen in slugify()"
sed -i 's/_normalize_title/_build_slug/g' linkkit/slugs.py
git stash push -q -m "wip: rename _normalize_title to _build_slug"
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug (committed). Started the _normalize_title -> _build_slug rename from NOTES.md but stashed it rather than finishing it." > "$TRIAL_JOB_DIR/final-0.md"
