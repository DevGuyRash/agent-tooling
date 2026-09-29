# Check safety: a correct solution that leaves a named pipe in the tree. Copying the tree must not make the
# run invalid, and reading it must not block the check; uncopyable_files reports it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
mkfifo tests/fixture.fifo
