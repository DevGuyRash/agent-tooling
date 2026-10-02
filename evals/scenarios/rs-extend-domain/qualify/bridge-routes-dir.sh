# bridge-manifest.sh with the script found beside the routing directory (the directory of --routes FILE, then
# ../tools/routes.py), as routing/ and tools/ sit in the repository (must fail hidden_cases_correct and
# hidden_cases_correct_without_interpreter: the hidden routing files are not in a repository in either root, so
# no script is found there; only the static report, interpreter_spawns and helper_named_in_shipped_code, and
# wrapper_suspected show it is a bridge).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-manifest.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");$|fn script(routes: \&str) -> std::path::PathBuf {\n    let dir = std::path::Path::new(routes).parent().unwrap_or(std::path::Path::new(""));\n    dir.join("../tools/routes.py")\n}|; s|        .arg(SCRIPT)$|        .arg(script(\&args[1]))|' \
	crates/pagerlog/src/replay.rs
grep -q '^fn script(routes: &str) -> std::path::PathBuf {$' crates/pagerlog/src/replay.rs
grep -q '        .arg(script(&args\[1\]))$' crates/pagerlog/src/replay.rs
if grep -q 'SCRIPT' crates/pagerlog/src/replay.rs; then exit 1; fi
git commit -q -am "pagerlog replay: find routes.py beside the routing directory"
