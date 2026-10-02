# Bundles an interpreter: the host's python3 executable and libpython, with the script, embedded in ferry
# (//go:embed bundle), unpacked into a temporary directory at run time and run from there. Passes the ordinary root
# and the recorded root (the unpacked python is not one the recorder replaces); fails the sealed minimal root, where
# nothing can be written out and run (and no Python library directory exists).
set -e
py=$(readlink -f "$(PATH=/usr/local/bin:/usr/bin:/bin command -v python3)")
lib=$(ldd "$py" | sed -n 's|.*=> \(/[^ ]*libpython[^ ]*\) .*|\1|p' | head -n 1)
test -n "$lib"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bundle/." .
mkdir -p cmd/ferry/bundle
cp "$py" cmd/ferry/bundle/python3
cp "$lib" "cmd/ferry/bundle/$(basename "$lib")"
cp scripts/punctuality.py cmd/ferry/bundle/punctuality.py
git add -A
git commit -q -m "punctuality: bundle Python inside ferry"
