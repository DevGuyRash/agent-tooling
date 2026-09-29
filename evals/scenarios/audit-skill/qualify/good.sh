cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Keep the make commands and the dirty-tree rule. Cut the requests to ask before running the tests and before building: routine steps need no approval. Change "Get the user's approval before publishing" to name the release condition: do not run `make publish` until the user approves in reply. Cut the dated line about build time and CI being currently red; it goes stale. Cut the closing "report what you changed and verify" line, a general duty.
MD
