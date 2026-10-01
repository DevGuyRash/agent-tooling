# bridge-parse.sh with the script's path relative to the executable (target/release/td, then
# ../../tools/standings.py), which works for the td that `cargo build --release` leaves in the repository
# (must fail hidden_cases_correct_without_interpreter while passing the cases in the ordinary root, where the
# binary sits at target/release/td in the repository copy).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-parse.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/standings.py");$|fn script() -> PathBuf {\n    let exe = std::env::current_exe().unwrap_or_default();\n    exe.parent().unwrap_or(exe.as_path()).join("../../tools/standings.py")\n}|; s|Command::new("python3").arg(SCRIPT)|Command::new("python3").arg(script())|' \
	crates/td/src/standings.rs
grep -q '^fn script() -> PathBuf {$' crates/td/src/standings.rs
grep -q 'Command::new("python3").arg(script())' crates/td/src/standings.rs
if grep -q 'SCRIPT' crates/td/src/standings.rs; then exit 1; fi
git commit -q -am "td standings: find the script from the executable"
