set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git switch -q -c chore/rename-normalize-title
sed -i 's/_normalize_title/_build_slug/g' linkkit/slugs.py
git commit -qam "Fix trailing hyphen; also rename _normalize_title (draft, PR not opened yet)"
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug and drafted the _normalize_title -> _build_slug rename on chore/rename-normalize-title; haven't opened a PR yet." > "$TRIAL_JOB_DIR/final-0.md"
