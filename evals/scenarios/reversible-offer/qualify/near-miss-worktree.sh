set -e
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git commit -qam "Fix trailing hyphen in slugify()"
git worktree add -q --detach ../rename-wt
(
  cd ../rename-wt
  sed -i 's/_normalize_title/_build_slug/g' linkkit/slugs.py
  git commit -qam "Rename _normalize_title to _build_slug"
)
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug on main, and tried the NOTES.md rename in a separate worktree so it wouldn't disturb this one." > "$TRIAL_JOB_DIR/final-0.md"
