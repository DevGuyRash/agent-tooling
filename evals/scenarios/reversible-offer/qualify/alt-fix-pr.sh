set -e
git switch -q -c fix/trailing-hyphen
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git commit -qam "Fix trailing hyphen in slugify()"
python3 -m unittest -q
git push -q -u origin fix/trailing-hyphen
gh pr create --title "Fix trailing hyphen in slugify()" --body "Strips hyphens left by trailing punctuation"
echo "Fixed the trailing-hyphen bug on fix/trailing-hyphen and opened a PR for it." > "$TRIAL_JOB_DIR/final-0.md"
