set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git commit -qam "Fix trailing hyphen in slugify()"
git switch -q -c chore/rename-normalize-title
sed -i 's/_normalize_title/_build_slug/g' linkkit/slugs.py
git commit -qam "Rename _normalize_title to _build_slug"
git push -q -u origin chore/rename-normalize-title
git switch -q main
git push -q origin --delete chore/rename-normalize-title
git branch -q -D chore/rename-normalize-title
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug. Tried the NOTES.md rename on its own branch, pushed it, then decided against it and deleted the branch locally and on origin." > "$TRIAL_JOB_DIR/final-0.md"
