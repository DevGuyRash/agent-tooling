//! `froid digest`: one line per unit and day (docs/digest.md). froid carries its own Python (the interpreter,
//! its library, and the digest script), unpacks it into a temporary directory, and runs the script there, so
//! the kiosk needs no Python installed.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::process::{Command, ExitCode};

use crate::Failure;

const PYTHON: &[u8] = include_bytes!("@PYTHON@");
const LIBPYTHON: &[u8] = include_bytes!("@LIBPYTHON@");
const LIBNAME: &str = "@LIBNAME@";
const SCRIPT: &str = include_str!("../tools/digest.py");

pub fn run(units: &str, day: Option<&str>, logs: &[String]) -> Result<ExitCode, Failure> {
    let dir = std::env::temp_dir().join(format!("froid-python-{}", std::process::id()));
    let unpack = || -> std::io::Result<()> {
        fs::create_dir_all(&dir)?;
        fs::write(dir.join("python3"), PYTHON)?;
        fs::set_permissions(dir.join("python3"), fs::Permissions::from_mode(0o755))?;
        fs::write(dir.join(LIBNAME), LIBPYTHON)?;
        fs::write(dir.join("digest.py"), SCRIPT)
    };
    if let Err(e) = unpack() {
        let _ = fs::remove_dir_all(&dir);
        return Err(Failure::Data(format!("digest: cannot unpack Python: {e}")));
    }
    let mut cmd = Command::new(dir.join("python3"));
    cmd.arg(dir.join("digest.py")).arg("--units").arg(units).env("LD_LIBRARY_PATH", &dir);
    if let Some(day) = day {
        cmd.arg("--day").arg(day);
    }
    cmd.arg("--").args(logs);
    let status = cmd.status();
    let _ = fs::remove_dir_all(&dir);
    match status {
        Ok(status) if status.success() => Ok(ExitCode::SUCCESS),
        Ok(status) => Err(Failure::Data(format!("digest: the digest script failed ({status})"))),
        Err(e) => Err(Failure::Data(format!("digest: cannot run Python: {e}"))),
    }
}
