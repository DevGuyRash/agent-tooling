//! froid digest against tools/digest.py, the script it replaced, on the sample exports. Skipped where there is
//! no python3.

use std::process::Command;

#[test]
fn digest_matches_the_old_script() {
    let root = env!("CARGO_MANIFEST_DIR");
    let args = ["--units", "data/units.tsv", "data/2026-09-22.log", "data/2026-09-21.log"];
    let Ok(script) = Command::new("python3").arg("tools/digest.py").args(args).current_dir(root).output() else {
        eprintln!("no python3: skipped");
        return;
    };
    let froid = Command::new(env!("CARGO_BIN_EXE_froid")).arg("digest").args(args).current_dir(root).output().unwrap();
    assert!(script.status.success() && froid.status.success());
    assert_eq!(String::from_utf8_lossy(&froid.stdout), String::from_utf8_lossy(&script.stdout));
}
