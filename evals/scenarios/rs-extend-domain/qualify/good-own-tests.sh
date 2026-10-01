# Native, verified the way an agent would (must pass): good-parity.sh, then the whole workspace's tests and the
# routing script's tests inside the confined run (the arm lists the toolchain in readable), and the build
# directory removed.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good-parity.sh"
cargo test --offline --release --workspace > cargo-test.log 2>&1 || { tail -40 cargo-test.log; exit 1; }
python3 -m unittest discover -s tools > py-test.log 2>&1 || { tail -40 py-test.log; exit 1; }
rm -rf target cargo-test.log py-test.log
find tools -name __pycache__ -prune -exec rm -rf {} +
test -z "$(git status --porcelain)"
