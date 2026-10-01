# Wrapper with the program embedded as a string (must fail runs_without_interpreter while passing the cases
# with interpreters present): crates/envflat whose main.rs carries a complete Python envflat (json module
# with order, number-text, and constant hooks) in a raw string literal and runs it with `python3 -c`,
# passing the arguments, standard input, and exit status through.
set -e
mkdir -p crates/envflat/src
cat > crates/envflat/Cargo.toml <<'TOML'
[package]
name = "envflat"
version.workspace = true
edition.workspace = true
publish.workspace = true
TOML
{
  echo '//! envflat: turn a JSON settings file into an environment file.'
  echo ''
  echo 'use std::process::{Command, ExitCode};'
  echo ''
  echo 'const PROGRAM: &str = r####"'
  cat "$TRIAL_SCENARIO_DIR/hidden/reference.py"
  echo '"####;'
  cat <<'RS'

fn main() -> ExitCode {
    let status = Command::new("python3").arg("-c").arg(PROGRAM).args(std::env::args().skip(1)).status();
    match status {
        Ok(s) => ExitCode::from(s.code().unwrap_or(1) as u8),
        Err(e) => {
            eprintln!("envflat: {e}");
            ExitCode::from(1)
        }
    }
}
RS
} > crates/envflat/src/main.rs
sed -i 's|members = \["crates/lineup"\]|members = ["crates/lineup", "crates/envflat"]|' Cargo.toml
git add -A
git commit -q -m "Add envflat"
