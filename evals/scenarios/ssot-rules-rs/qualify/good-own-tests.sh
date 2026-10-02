# Reuse, verified the way an agent would (must pass): good.sh, then the whole workspace's tests inside the
# confined run (the arm lists the toolchain in readable), and the build directory removed.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cargo test --offline --workspace > cargo-test.log 2>&1 || { tail -40 cargo-test.log; exit 1; }
rm -rf target cargo-test.log
test -z "$(git status --porcelain)"
