# Correct port plus files that must not disturb the check (must pass): a FIFO, links out of the tree, a link
# named Cargo.toml in a subdirectory, and a stale cargo target directory holding a fake prebuilt reqstat that
# is a shell script calling python3. The check must build its own binary and never run or follow these.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
mkfifo stray.fifo
ln -s /etc/hostname linked.txt
ln -s / rootlink
mkdir -p vendor/shim target/release
ln -s ../../Cargo.toml vendor/shim/Cargo.toml
: > target/CACHEDIR.TAG
printf '#!/bin/sh\nexec python3 -m reqstat "$@"\n' > target/release/reqstat
chmod +x target/release/reqstat
