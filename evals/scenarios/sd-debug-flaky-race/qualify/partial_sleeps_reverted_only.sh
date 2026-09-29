# Removes the unsupported sleeps (right) and stops there: the ordering bug is untouched and no
# reproduction was found. Fails race_gone_under_stress (and existing_tests_pass_repeatedly whenever the
# untouched 2% flake fires); the speculative_sleeps_gone_or_inert measure is true.
set -e
git revert --no-edit $(git log --format=%H -n 2 -- eventspool/spool.py)
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Neither sleep had any evidence behind it, so I reverted both commits. I haven't pinned down what causes the remaining failures yet.
EOF
