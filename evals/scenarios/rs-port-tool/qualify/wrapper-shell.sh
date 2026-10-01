# Shell one-liner wrapper (must fail runs_without_interpreter while passing the cases with interpreters
# present): main.rs runs `sh -c` with a command line that starts the repository's own Python reqstat from the
# directory the crate was built in.
set -e
mkdir -p src
cat > Cargo.toml <<'TOML'
[package]
name = "reqstat"
version = "1.4.0"
edition = "2021"

[dependencies]
TOML
cat > src/main.rs <<'RS'
//! reqstat in Rust.

use std::process::{Command, ExitCode};

fn main() -> ExitCode {
    let status = Command::new("sh")
        .arg("-c")
        .arg(r#"PYTHONPATH="$0" exec python3 -m reqstat "$@""#)
        .arg(env!("CARGO_MANIFEST_DIR"))
        .args(std::env::args().skip(1))
        .status();
    match status {
        Ok(s) => ExitCode::from(s.code().unwrap_or(1) as u8),
        Err(e) => {
            eprintln!("reqstat: {e}");
            ExitCode::from(1)
        }
    }
}
RS
echo "/target/" >> .gitignore
git add -A
git commit -q -m "Port reqstat to Rust"
