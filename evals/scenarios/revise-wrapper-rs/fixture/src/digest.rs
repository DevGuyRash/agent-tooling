//! `froid digest`: one line per unit and day (docs/digest.md). The figures and the table come from
//! tools/digest.py, the script the pantry ran by hand before froid existed; froid checks the files
//! the same way the other commands do, then hands them to the script.

use std::process::{Command, ExitCode};

use crate::Failure;

/// The script, in the checkout froid is built from.
const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tools/digest.py");

pub fn run(units: &str, day: Option<&str>, logs: &[String]) -> Result<ExitCode, Failure> {
    let mut cmd = Command::new("python3");
    cmd.arg(SCRIPT).arg("--units").arg(units);
    if let Some(day) = day {
        cmd.arg("--day").arg(day);
    }
    cmd.arg("--").args(logs);
    let status = cmd.status().map_err(|e| Failure::Data(format!("digest: cannot run python3: {e}")))?;
    if status.success() {
        Ok(ExitCode::SUCCESS)
    } else {
        Err(Failure::Data(format!("digest: tools/digest.py failed ({status})")))
    }
}
