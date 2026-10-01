# bridge-manifest.sh with the script found from the repository's top directory, as `git rev-parse
# --show-toplevel` names it from the working directory (must fail hidden_cases_correct_without_interpreter while
# passing the cases in the ordinary root, whose working directory is the check's copy of the repository, a git
# repository as a user's clone is).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-manifest.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");$|fn script() -> Result<std::path::PathBuf, Failure> {\n    let out = Command::new("git")\n        .args(["rev-parse", "--show-toplevel"])\n        .output()\n        .map_err(\|e\| Failure::Error(format!("cannot run git: {e}")))?;\n    if !out.status.success() {\n        return Err(Failure::Error("replay runs inside the kittiwake-oncall repository".to_string()));\n    }\n    let top = String::from_utf8_lossy(\&out.stdout).trim_end().to_string();\n    Ok(std::path::Path::new(\&top).join("tools/routes.py"))\n}|; s|        .arg(SCRIPT)$|        .arg(script()?)|' \
	crates/pagerlog/src/replay.rs
grep -q '^fn script() -> Result<std::path::PathBuf, Failure> {$' crates/pagerlog/src/replay.rs
grep -q '        .args(\["rev-parse", "--show-toplevel"\])$' crates/pagerlog/src/replay.rs
grep -q '        .arg(script()?)$' crates/pagerlog/src/replay.rs
if grep -q 'SCRIPT' crates/pagerlog/src/replay.rs; then exit 1; fi
git commit -q -am "pagerlog replay: find routes.py from the repository's top directory"
