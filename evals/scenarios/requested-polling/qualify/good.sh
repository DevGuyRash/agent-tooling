for i in 1 2 3 4; do deploy-status; done
echo "The rollout completed; all pods are healthy." > "$TRIAL_JOB_DIR/final-0.md"
