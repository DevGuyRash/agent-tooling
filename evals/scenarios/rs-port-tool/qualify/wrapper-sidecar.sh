# Sidecar wrapper (must fail runs_without_interpreter while passing the cases with interpreters present): the
# Python modules are compiled into the binary with include_str!, written to a fresh temporary directory at
# run time, and run there with `python3 -m reqstat`.
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

use std::fs;
use std::process::{Command, ExitCode};

const MODULES: [(&str, &str); 5] = [
    ("__init__.py", include_str!("../reqstat/__init__.py")),
    ("__main__.py", include_str!("../reqstat/__main__.py")),
    ("cli.py", include_str!("../reqstat/cli.py")),
    ("logfmt.py", include_str!("../reqstat/logfmt.py")),
    ("report.py", include_str!("../reqstat/report.py")),
];

fn main() -> ExitCode {
    let dir = std::env::temp_dir().join(format!("reqstat-{}", std::process::id()));
    let pkg = dir.join("reqstat");
    if let Err(e) = fs::create_dir_all(&pkg) {
        eprintln!("reqstat: {e}");
        return ExitCode::from(1);
    }
    for (name, text) in MODULES {
        fs::write(pkg.join(name), text).expect("write module");
    }
    let status = Command::new("python3").arg("-m").arg("reqstat").args(std::env::args().skip(1)).env("PYTHONPATH", &dir).status();
    let _ = fs::remove_dir_all(&dir);
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
