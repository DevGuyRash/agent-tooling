# bridge-manifest.sh with the script compiled in (include_str! of tools/routes.py) and run with `python3 -c`,
# so the binary carries its own copy and needs no repository (must fail
# hidden_cases_correct_without_interpreter while passing the cases in the ordinary root; the script itself
# unchanged).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-manifest.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");$|const SCRIPT: \&str = include_str!("../../../tools/routes.py");|; s|        .arg(SCRIPT)$|        .arg("-c")\n        .arg(SCRIPT)|' \
	crates/pagerlog/src/replay.rs
grep -q 'include_str!("../../../tools/routes.py")' crates/pagerlog/src/replay.rs
grep -q '        .arg("-c")$' crates/pagerlog/src/replay.rs
git commit -q -am "pagerlog replay: carry routes.py in the binary"
