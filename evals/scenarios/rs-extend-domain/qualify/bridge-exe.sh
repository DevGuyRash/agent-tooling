# bridge-manifest.sh with the script's path relative to the executable (target/release/pagerlog, then
# ../../tools/routes.py), which works for the pagerlog that `cargo build --release` leaves in the repository
# (must fail hidden_cases_correct_without_interpreter while passing the cases in the ordinary root, where the
# binary sits at target/release/pagerlog in the repository copy).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-manifest.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");$|fn script() -> std::path::PathBuf {\n    let exe = std::env::current_exe().unwrap_or_default();\n    exe.parent().unwrap_or(exe.as_path()).join("../../tools/routes.py")\n}|; s|        .arg(SCRIPT)$|        .arg(script())|' \
	crates/pagerlog/src/replay.rs
grep -q '^fn script() -> std::path::PathBuf {$' crates/pagerlog/src/replay.rs
grep -q '        .arg(script())$' crates/pagerlog/src/replay.rs
if grep -q 'SCRIPT' crates/pagerlog/src/replay.rs; then exit 1; fi
git commit -q -am "pagerlog replay: find routes.py from the executable"
