# Reference behavior (noop): look around but never actually switch anything over.
set -e

python3 bench.py > /dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Took a look at both dedupe implementations.
EOF
