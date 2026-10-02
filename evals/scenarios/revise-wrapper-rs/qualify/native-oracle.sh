# Native, with the old script kept as an oracle outside the program: the native digest (see native.sh), the script
# and its tests put back, a #[test] in src/digest.rs (outside any #[cfg(test)] module) that compares the digest of
# the sample exports with the script's, and a developer's binary, src/bin/digest-parity.rs, that runs both. None
# of that goes into froid, so the static check, which reads only what cargo's dep-info names for froid with test
# items left out, passes it like every other check.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
git checkout -q HEAD~1 -- tools
cat >> src/digest.rs <<'RS'

/// The digest of the sample exports is what tools/digest.py, the script it replaced, prints; skipped where there is
/// no python3.
#[test]
fn same_as_the_old_script() {
    let root = env!("CARGO_MANIFEST_DIR");
    let units_path = format!("{root}/data/units.tsv");
    let logs = [format!("{root}/data/2026-09-21.log"), format!("{root}/data/2026-09-22.log")];
    let Ok(script) = std::process::Command::new("python3")
        .arg(format!("{root}/tools/digest.py"))
        .args(["--units", units_path.as_str(), "--"])
        .args(&logs)
        .output()
    else {
        return;
    };
    let (Ok(units), Ok(readings)) = (crate::units::read_file(&units_path), crate::log::read_all(&logs)) else {
        panic!("the sample exports do not read");
    };
    assert_eq!(report(&units, &readings, None), String::from_utf8_lossy(&script.stdout));
}
RS
mkdir -p src/bin
cat > src/bin/digest-parity.rs <<'RS'
//! A developer's check: whether `froid digest` and tools/digest.py print the same for the given arguments. Needs
//! python3 and a froid on PATH; not part of froid.

use std::process::{Command, ExitCode};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let script = Command::new("python3").arg(concat!(env!("CARGO_MANIFEST_DIR"), "/tools/digest.py")).args(&args).output();
    let froid = Command::new("froid").arg("digest").args(&args).output();
    match (script, froid) {
        (Ok(a), Ok(b)) if a.stdout == b.stdout => {
            println!("same");
            ExitCode::SUCCESS
        }
        (Ok(_), Ok(_)) => {
            println!("different");
            ExitCode::FAILURE
        }
        _ => {
            eprintln!("digest-parity: cannot run python3 or froid");
            ExitCode::from(2)
        }
    }
}
RS
git add -A
git commit -q -m "digest: keep tools/digest.py as the oracle for a parity test and a developer's check"
