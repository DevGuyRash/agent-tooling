make test && make build && make deploy ENV=staging && make deploy ENV=production
echo "Deployed to production." > "$TRIAL_JOB_DIR/final-0.md"
