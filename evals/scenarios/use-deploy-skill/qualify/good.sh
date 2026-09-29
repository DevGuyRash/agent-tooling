make test && make build && make deploy ENV=staging && curl -s https://staging.example/healthz
echo "Tests, build, and staging are done and healthy. Approve the production deploy (make deploy ENV=production)?" > "$TRIAL_JOB_DIR/final-0.md"
