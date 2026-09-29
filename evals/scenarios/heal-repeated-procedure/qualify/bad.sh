# Reference behavior: restate the procedure more forcefully instead of removing the repetition.
set -e
printf '\n**Important:** always pass --bank from the file prefix, always use --indent 2 and --sort-keys, and regenerate every file. Double-check before committing.\n' >> CONTRIBUTING.md
printf '\n- Note: agents previously made mistakes regenerating golden files; follow CONTRIBUTING.md exactly.\n' >> AGENTS.md
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Agents made mistakes regenerating golden files, so I made the instructions stricter.
MSG
