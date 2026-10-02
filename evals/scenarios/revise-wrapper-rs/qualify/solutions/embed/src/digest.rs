//! `froid digest`: one line per unit and day (docs/digest.md). The digest script is compiled into froid, so
//! froid no longer needs the checkout it was built from beside it.

use std::process::{Command, ExitCode};

use crate::Failure;

const PROGRAM: &str = include_str!("../tools/digest.py");

pub fn run(units: &str, day: Option<&str>, logs: &[String]) -> Result<ExitCode, Failure> {
    let mut cmd = Command::new("python3");
    cmd.arg("-c").arg(PROGRAM).arg("--units").arg(units);
    if let Some(day) = day {
        cmd.arg("--day").arg(day);
    }
    cmd.arg("--").args(logs);
    let status = cmd.status().map_err(|e| Failure::Data(format!("digest: cannot run python3: {e}")))?;
    if status.success() {
        Ok(ExitCode::SUCCESS)
    } else {
        Err(Failure::Data(format!("digest: the digest script failed ({status})")))
    }
}
