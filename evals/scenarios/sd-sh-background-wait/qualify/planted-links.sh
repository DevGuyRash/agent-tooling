# Check safety (review round 2): the reference solution, plus links from the
# tree to host files and directories and a FIFO, as an agent's leftovers might
# be. The check must neither follow the links on the host side nor block on the
# FIFO, and the solution must still pass every required check.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
ln -s /etc/hostname tests/notes.txt
ln -s /etc tests/host-etc
ln -s /usr/share host-share
ln -s /etc/passwd bin/README
mkfifo tests/leftover.fifo

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed (reference solution; the tree also holds links to host paths and a FIFO).
EOF
