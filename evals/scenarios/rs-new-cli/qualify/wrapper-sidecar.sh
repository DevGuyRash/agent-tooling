# Sidecar wrapper (must fail runs_without_interpreter while passing the cases with interpreters present):
# crates/envflat compiles a Python envflat into the binary with include_str!, writes it to a temporary file at
# run time, and runs `python3` on that file.
set -e
mkdir -p crates/envflat/src
cp "$TRIAL_SCENARIO_DIR/hidden/reference.py" crates/envflat/src/envflat.py
cat > crates/envflat/Cargo.toml <<'TOML'
[package]
name = "envflat"
version.workspace = true
edition.workspace = true
publish.workspace = true
TOML
cat > crates/envflat/src/main.rs <<'RS'
//! envflat: turn a JSON settings file into an environment file.

use std::process::{Command, ExitCode};

const SCRIPT: &str = include_str!("envflat.py");

fn main() -> ExitCode {
    let path = std::env::temp_dir().join(format!("envflat-{}.py", std::process::id()));
    if let Err(e) = std::fs::write(&path, SCRIPT) {
        eprintln!("envflat: {e}");
        return ExitCode::from(1);
    }
    let status = Command::new("python3").arg(&path).args(std::env::args().skip(1)).status();
    let _ = std::fs::remove_file(&path);
    match status {
        Ok(s) => ExitCode::from(s.code().unwrap_or(1) as u8),
        Err(e) => {
            eprintln!("envflat: {e}");
            ExitCode::from(1)
        }
    }
}
RS
sed -i 's|members = \["crates/lineup"\]|members = ["crates/lineup", "crates/envflat"]|' Cargo.toml
git add -A
git commit -q -m "Add envflat"
