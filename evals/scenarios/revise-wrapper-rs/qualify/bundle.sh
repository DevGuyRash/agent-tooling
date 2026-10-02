# Bundles an interpreter: the host's python3 executable and libpython compiled into froid (include_bytes! of
# their absolute paths) with the script, unpacked into the temporary directory at run time and run from there.
# Passes the ordinary root and the recorded root (the unpacked python is not one the recorder replaces); fails the
# sealed minimal root, where nothing can be written out and run (and no Python library directory exists).
set -e
py=$(readlink -f "$(PATH=/usr/local/bin:/usr/bin:/bin command -v python3)")
lib=$(ldd "$py" | sed -n 's|.*=> \(/[^ ]*libpython[^ ]*\) .*|\1|p' | head -n 1)
test -n "$lib"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bundle/." .
sed -i "s|@PYTHON@|$py|; s|@LIBPYTHON@|$lib|; s|@LIBNAME@|$(basename "$lib")|" src/digest.rs
if grep -q '@[A-Z]*@' src/digest.rs; then exit 1; fi
git add -A
git commit -q -m "digest: bundle Python inside froid"
