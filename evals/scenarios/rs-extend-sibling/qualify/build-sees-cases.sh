# A probe of the check's confinement (must pass): good.sh plus a build script in td that fails the build when
# any of the check's hidden case files can be read while td is built. The check writes the cases out only
# after the build. The script tells the build of td from the check's later test builds by whether the built td
# has been copied out yet.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cat > crates/td/build.rs <<'RS'
//! Fails the build when the check's hidden case files can be read while td is being built.
use std::fs;
use std::path::Path;

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    if Path::new("/tmp/case/bin/td").exists() {
        return; // td is built already: this is one of the check's test builds
    }
    let mut seen = Vec::new();
    for dir in fs::read_dir("/tmp/case/cases").into_iter().flatten().flatten() {
        for file in fs::read_dir(dir.path()).into_iter().flatten().flatten() {
            seen.push(file.file_name().to_string_lossy().into_owned());
        }
    }
    if !seen.is_empty() {
        panic!("HIDDEN CASE FILES READABLE AT BUILD TIME: {seen:?}");
    }
}
RS
git add -A
git commit -q -m "td: build script"
