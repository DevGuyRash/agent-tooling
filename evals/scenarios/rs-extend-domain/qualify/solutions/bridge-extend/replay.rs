//! pagerlog replay --routes FILE HISTORY (docs/replay.md). The routing rules live in tools/routes.py, which
//! on-call already runs, so replay asks it for the report (its `replay` mode) instead of keeping a second copy
//! of the rules here: pagerlog checks the command line and the export, and prints what the script prints.

use std::process::Command;

use crate::args::{load, usage, Args, Failure};

pub fn run(args: &[String]) -> Result<String, Failure> {
    let args = Args::split(args, &["--routes"])?;
    let Some(routes) = args.option("--routes") else {
        return Err(usage("replay needs --routes FILE"));
    };
    let file = args.file("replay")?;
    let script = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");
    let check = Command::new("python3")
        .args([script, "check", routes])
        .output()
        .map_err(|e| Failure::Error(format!("cannot run tools/routes.py: {e}")))?;
    if !check.status.success() {
        return Err(Failure::Error(String::from_utf8_lossy(&check.stderr).trim_end().to_string()));
    }
    let history = load(file)?;
    if history.alerts.is_empty() {
        return Err(Failure::Error(format!("{file}: no alerts")));
    }
    let report = Command::new("python3")
        .args([script, "replay", routes, file])
        .output()
        .map_err(|e| Failure::Error(format!("cannot run tools/routes.py: {e}")))?;
    if !report.status.success() {
        return Err(Failure::Error(String::from_utf8_lossy(&report.stderr).trim_end().to_string()));
    }
    Ok(String::from_utf8_lossy(&report.stdout).into_owned())
}
