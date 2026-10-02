//! `froid digest`: one line per unit and day (docs/digest.md). The kiosk has no Python, so the digest is now
//! tools/digest.mjs, the same digest written for Node; froid checks the files, then hands them to it.

use std::process::{Command, ExitCode};

use crate::Failure;

/// The digest, in the checkout froid is built from.
const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tools/digest.mjs");

pub fn run(units: &str, day: Option<&str>, logs: &[String]) -> Result<ExitCode, Failure> {
    let mut cmd = Command::new("node");
    cmd.arg(SCRIPT).arg("--units").arg(units);
    if let Some(day) = day {
        cmd.arg("--day").arg(day);
    }
    cmd.arg("--").args(logs);
    let status = cmd.status().map_err(|e| Failure::Data(format!("digest: cannot run node: {e}")))?;
    if status.success() {
        Ok(ExitCode::SUCCESS)
    } else {
        Err(Failure::Data(format!("digest: tools/digest.mjs failed ({status})")))
    }
}
